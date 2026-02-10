#!/usr/bin/env python3
"""
Update Username in Bot Database and Rename Folder
Keeps bot's folder structure and database synchronized with Instagram username changes
"""

import sqlite3
from pathlib import Path


def update_username_in_bot(device_serial, old_username, new_username):
    """
    Update username across all bot databases and rename account folder

    When a username changes on Instagram, this function:
    1. Updates the accounts.db database (if exists)
    2. Renames the account folder from old_username to new_username

    Args:
        device_serial: Device ID (e.g., "10.1.10.36_5555")
        old_username: Current/old username
        new_username: New username (after Instagram change)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'renamed_folder': str (if success),
            'updated_db': bool
        }
    """
    try:
        # uiAutomator is now inside dashboard, so 2 levels up for device folders
        base_dir = Path(__file__).parent.parent.parent
        device_dir = base_dir / device_serial

        print(f"\n{'='*70}")
        print(f"UPDATING BOT DATABASE: {old_username} → {new_username}")
        print(f"{'='*70}")

        # 1. Validate old folder exists
        old_folder = device_dir / old_username
        if not old_folder.exists():
            error_msg = f"Old account folder not found: {old_folder}"
            print(f"✗ {error_msg}")
            return {
                'success': False,
                'message': error_msg,
                'updated_db': False
            }

        print(f"✓ Found old account folder: {old_folder}")

        # 2. Check if new folder already exists (collision)
        new_folder = device_dir / new_username
        if new_folder.exists():
            error_msg = f"New account folder already exists: {new_folder}"
            print(f"✗ {error_msg}")
            return {
                'success': False,
                'message': error_msg,
                'updated_db': False
            }

        # 3. Update accounts.db (if exists)
        db_updated = False
        accounts_db = device_dir / "accounts.db"

        if accounts_db.exists():
            print(f"\n--- Updating accounts.db ---")
            try:
                conn = sqlite3.connect(accounts_db)
                cursor = conn.cursor()

                # Update username in accounts table
                cursor.execute('''
                    UPDATE accounts
                    SET account = ?
                    WHERE account = ?
                ''', (new_username, old_username))

                rows_updated = cursor.rowcount
                conn.commit()
                conn.close()

                if rows_updated > 0:
                    print(f"✓ Updated {rows_updated} row(s) in accounts.db")
                    db_updated = True
                else:
                    print(f"⚠ No rows updated (account '{old_username}' not found in accounts.db)")
                    # Not critical - account might not be in scheduler

            except Exception as e:
                print(f"⚠ Warning: Error updating accounts.db: {e}")
                # Continue anyway - folder rename is more important

        else:
            print(f"⚠ accounts.db not found - skipping database update")
            # Not critical - some setups might not use accounts.db

        # 4. Rename account folder
        print(f"\n--- Renaming Account Folder ---")
        print(f"From: {old_folder.name}")
        print(f"To:   {new_folder.name}")

        try:
            old_folder.rename(new_folder)
            print(f"✓ Folder renamed successfully!")

            # Verify the rename worked
            if new_folder.exists() and not old_folder.exists():
                print(f"✓ Verified: New folder exists, old folder gone")

                print(f"\n{'='*70}")
                print(f"SUCCESS: Bot database synchronized with Instagram")
                print(f"{'='*70}")
                print(f"Username: {old_username} → {new_username}")
                print(f"Folder:   {old_folder.name} → {new_folder.name}")
                print(f"Database: {'Updated' if db_updated else 'N/A'}")
                print(f"{'='*70}\n")

                return {
                    'success': True,
                    'message': f'Successfully updated username from {old_username} to {new_username}',
                    'renamed_folder': str(new_folder),
                    'updated_db': db_updated
                }
            else:
                raise Exception("Folder rename verification failed")

        except Exception as e:
            error_msg = f"Error renaming folder: {e}"
            print(f"✗ {error_msg}")

            # Try to rollback database update if folder rename failed
            if db_updated and accounts_db.exists():
                try:
                    print("Attempting to rollback database update...")
                    conn = sqlite3.connect(accounts_db)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE accounts
                        SET account = ?
                        WHERE account = ?
                    ''', (old_username, new_username))
                    conn.commit()
                    conn.close()
                    print("✓ Database update rolled back")
                except:
                    print("⚠ Could not rollback database update")

            return {
                'success': False,
                'message': error_msg,
                'updated_db': False
            }

    except Exception as e:
        error_msg = f'Unexpected error updating username: {e}'
        print(f"✗ {error_msg}")
        return {
            'success': False,
            'message': error_msg,
            'updated_db': False
        }


def main():
    """Example usage"""
    # Example: Update username for testing
    result = update_username_in_bot(
        device_serial="10.1.10.36_5555",
        old_username="test.old",
        new_username="test.new"
    )

    print("\nResult:")
    print(f"  Success: {result['success']}")
    print(f"  Message: {result['message']}")
    if result.get('renamed_folder'):
        print(f"  New folder: {result['renamed_folder']}")


if __name__ == "__main__":
    main()
