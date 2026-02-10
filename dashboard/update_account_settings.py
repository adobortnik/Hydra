#!/usr/bin/env python
# Helper function to update account settings in bulk
# This file is imported by simple_app.py

import os
import sqlite3
import sys
import traceback
import json

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def update_account_settings_bulk(base_dir, device_id, account_name, settings_to_update):
    """
    Update multiple settings for a specific account
    
    Args:
        base_dir (str): Base directory path
        device_id (str): Device ID
        account_name (str): Account name
        settings_to_update (dict): Dictionary of settings to update (key-value pairs)
    
    Returns:
        tuple: (success, error_message)
    """
    try:
        # Construct path to account's settings.db
        account_dir = os.path.join(base_dir, device_id, account_name)
        settings_db_path = os.path.join(account_dir, 'settings.db')
        
        # Check if the account directory exists
        if not os.path.exists(account_dir):
            return False, f"Account directory not found: {account_dir}"
        
        print(f"Processing account: {device_id}/{account_name}")
        print(f"Settings DB path: {settings_db_path}")
        
        # Check if the settings.db file exists
        if not os.path.exists(settings_db_path):
            print(f"Settings DB file does not exist, creating new one: {settings_db_path}")
            # Create a new settings.db file with default settings
            conn = get_db_connection(settings_db_path)
            cursor = conn.cursor()
            
            # Create the accountsettings table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS accountsettings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settings TEXT
            )
            ''')
            
            # Create default settings JSON
            default_settings = {}
            for key, value in settings_to_update.items():
                default_settings[key] = value
            
            # Insert the settings JSON
            cursor.execute(
                "INSERT INTO accountsettings (settings) VALUES (?)",
                (json.dumps(default_settings),)
            )
            
            conn.commit()
            conn.close()
            return True, "Created new settings.db with specified settings"
        
        # Connect to the existing settings.db
        conn = get_db_connection(settings_db_path)
        cursor = conn.cursor()
        
        # Check if the accountsettings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accountsettings'")
        if cursor.fetchone() is None:
            # Create the accountsettings table
            cursor.execute('''
            CREATE TABLE accountsettings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settings TEXT
            )
            ''')
            
            # Create default settings JSON
            default_settings = {}
            for key, value in settings_to_update.items():
                default_settings[key] = value
            
            # Insert the settings JSON
            cursor.execute(
                "INSERT INTO accountsettings (settings) VALUES (?)",
                (json.dumps(default_settings),)
            )
            
            conn.commit()
            conn.close()
            return True, "Created new accountsettings table with specified settings"
        
        # Get the current settings JSON
        cursor.execute("SELECT * FROM accountsettings LIMIT 1")
        row = cursor.fetchone()
        
        if row is None:
            # No settings row exists, create one
            default_settings = {}
            for key, value in settings_to_update.items():
                default_settings[key] = value
            
            cursor.execute(
                "INSERT INTO accountsettings (settings) VALUES (?)",
                (json.dumps(default_settings),)
            )
            
            conn.commit()
            conn.close()
            return True, "Created new settings row with specified settings"
        
        # Parse the existing settings JSON
        try:
            current_settings = json.loads(row['settings'])
            print(f"Current settings: {current_settings}")
        except json.JSONDecodeError:
            print(f"Error decoding JSON from settings column, creating new settings")
            current_settings = {}
        
        # Update the settings
        for key, value in settings_to_update.items():
            # Special handling for post_type_to_share
            if key == 'post_type_to_share':
                # Map the form values to the actual values used in the settings
                value_mapping = {
                    'post_reels': 'reels',
                    'post_photos': 'photos',
                    'post_all': 'all'
                }
                
                # Store the correct value based on the mapping
                mapped_value = value_mapping.get(value, value)  # Use original if not in mapping
                current_settings[key] = mapped_value
                
                print(f"Setting post_type_to_share to: {mapped_value} (from {value})")
                
                # Also set the individual post type flags based on the selection
                if value == 'post_reels':
                    current_settings['post_reels'] = True
                    current_settings['post_photos'] = False
                    current_settings['post_all'] = False
                elif value == 'post_photos':
                    current_settings['post_reels'] = False
                    current_settings['post_photos'] = True
                    current_settings['post_all'] = False
                elif value == 'post_all':
                    current_settings['post_reels'] = False
                    current_settings['post_photos'] = False
                    current_settings['post_all'] = True
            # Convert boolean strings to actual booleans for JSON
            elif isinstance(value, str) and value.lower() in ['true', 'false']:
                current_settings[key] = (value.lower() == 'true')
            else:
                current_settings[key] = value
        
        print(f"Updated settings: {current_settings}")
        
        # Save the updated settings back to the database
        cursor.execute(
            "UPDATE accountsettings SET settings = ? WHERE id = ?",
            (json.dumps(current_settings), row['id'])
        )
        
        conn.commit()
        conn.close()
        return True, "Settings updated successfully"
    
    except Exception as e:
        error_msg = f"Exception in update_account_settings_bulk: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return False, error_msg
