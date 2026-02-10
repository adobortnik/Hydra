#!/usr/bin/env python
# Script to update captions in account-specific scheduled post databases
# Replaces @christiannreal with @Christian.jagg in all scheduled posts

import os
import sqlite3
import sys
import glob

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def update_captions_in_account_db(db_path, old_text, new_text):
    """
    Update all captions in the account-specific scheduled_post table,
    replacing old_text with new_text
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # First, get all posts that contain the old text
        cursor.execute(
            "SELECT id, caption FROM scheduled_post WHERE caption LIKE ?", 
            (f'%{old_text}%',)
        )
        posts = cursor.fetchall()
        
        if not posts:
            print(f"No posts found containing '{old_text}' in {db_path}")
            conn.close()
            return 0
        
        print(f"Found {len(posts)} posts containing '{old_text}' in {db_path}")
        
        # Update each post
        updated_count = 0
        for post in posts:
            post_id = post['id']
            old_caption = post['caption']
            new_caption = old_caption.replace(old_text, new_text)
            
            cursor.execute(
                "UPDATE scheduled_post SET caption = ? WHERE id = ?",
                (new_caption, post_id)
            )
            updated_count += 1
            
            print(f"Updated post {post_id}")
            print(f"  Old caption: {old_caption[:50]}..." if len(old_caption) > 50 else f"  Old caption: {old_caption}")
            print(f"  New caption: {new_caption[:50]}..." if len(new_caption) > 50 else f"  New caption: {new_caption}")
            print("-" * 40)
        
        conn.commit()
        conn.close()
        return updated_count
    
    except Exception as e:
        print(f"Error updating captions in {db_path}: {e}")
        return 0

def find_account_dbs(base_dir):
    """Find all account-specific scheduled_post.db files"""
    account_dbs = []
    
    # Look for device directories (these are typically numeric)
    device_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    for device_dir in device_dirs:
        device_path = os.path.join(base_dir, device_dir)
        
        # Look for account directories within each device directory
        account_dirs = [d for d in os.listdir(device_path) if os.path.isdir(os.path.join(device_path, d))]
        
        for account_dir in account_dirs:
            account_path = os.path.join(device_path, account_dir)
            db_path = os.path.join(account_path, 'scheduled_post.db')
            
            if os.path.exists(db_path):
                account_dbs.append((device_dir, account_dir, db_path))
    
    return account_dbs

def main():
    # Get the absolute path to the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory (which should be the main tool directory)
    base_dir = os.path.dirname(current_dir)
    
    print(f"Looking for account databases in: {base_dir}")
    
    # Find all account-specific scheduled_post.db files
    account_dbs = find_account_dbs(base_dir)
    
    if not account_dbs:
        print("No account-specific databases found.")
        return 1
    
    print(f"Found {len(account_dbs)} account-specific databases:")
    for device_id, account_name, db_path in account_dbs:
        print(f"  Device: {device_id}, Account: {account_name}, DB: {db_path}")
    
    old_text = "@christiannreal"
    new_text = "@Christian.jagg"
    
    total_updated = 0
    
    # Update captions in each account-specific database
    for device_id, account_name, db_path in account_dbs:
        print(f"\nProcessing database for Device: {device_id}, Account: {account_name}")
        print(f"Database path: {db_path}")
        
        updated = update_captions_in_account_db(db_path, old_text, new_text)
        total_updated += updated
    
    if total_updated > 0:
        print(f"\nSuccessfully updated {total_updated} posts across {len(account_dbs)} account databases")
    else:
        print("\nNo posts were updated in any account database")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
