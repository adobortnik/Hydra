#!/usr/bin/env python
# Script to sync captions from the dashboard database to account-specific databases
# This will ensure all captions are consistent across both systems

import os
import sqlite3
import sys
import glob

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_dashboard_posts(db_path):
    """
    Get all posts from the dashboard database with their captions
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, deviceid, account, caption FROM scheduled_posts")
        posts = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return posts
    except Exception as e:
        print(f"Error getting posts from dashboard database: {e}")
        return []

def update_account_caption(db_path, post_id, caption):
    """
    Update the caption for a specific post in an account-specific database
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if the post exists in this account database
        cursor.execute("SELECT id, caption FROM scheduled_post WHERE post_id = ?", (post_id,))
        result = cursor.fetchone()
        
        if result:
            # Show the current caption for verification
            current_caption = result['caption']
            print(f"Current caption: {current_caption[:50]}..." if len(current_caption) > 50 else f"Current caption: {current_caption}")
            print(f"New caption: {caption[:50]}..." if len(caption) > 50 else f"New caption: {caption}")
            
            # Update the caption
            cursor.execute(
                "UPDATE scheduled_post SET caption = ? WHERE post_id = ?",
                (caption, post_id)
            )
            conn.commit()
            conn.close()
            return True
        else:
            conn.close()
            return False
    except Exception as e:
        print(f"Error updating caption in {db_path}: {e}")
        return False

def find_account_dbs(base_dir):
    """Find all account-specific scheduled_post.db files"""
    account_dbs = []
    
    # Look for device directories (these are typically numeric)
    device_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    for device_dir in device_dirs:
        device_path = os.path.join(base_dir, device_dir)
        
        # Look for account directories within each device directory
        try:
            account_dirs = [d for d in os.listdir(device_path) if os.path.isdir(os.path.join(device_path, d))]
            
            for account_dir in account_dirs:
                account_path = os.path.join(device_path, account_dir)
                db_path = os.path.join(account_path, 'scheduled_post.db')
                
                if os.path.exists(db_path):
                    account_dbs.append((device_dir, account_dir, db_path))
        except Exception as e:
            # Skip directories that can't be accessed
            print(f"Skipping directory {device_path}: {e}")
    
    return account_dbs

def main():
    # Get the absolute path to the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory (which should be the main tool directory)
    base_dir = os.path.dirname(current_dir)
    
    # Path to the dashboard scheduled posts database
    scheduled_posts_dir = os.path.join(base_dir, 'scheduled_posts')
    dashboard_db_path = os.path.join(scheduled_posts_dir, 'scheduled_posts.db')
    
    if not os.path.exists(dashboard_db_path):
        print(f"Error: Dashboard database not found at {dashboard_db_path}")
        return 1
    
    print(f"Reading posts from dashboard database: {dashboard_db_path}")
    dashboard_posts = get_dashboard_posts(dashboard_db_path)
    
    if not dashboard_posts:
        print("No posts found in dashboard database.")
        return 1
    
    print(f"Found {len(dashboard_posts)} posts in dashboard database.")
    
    # Find all account-specific scheduled_post.db files
    account_dbs = find_account_dbs(base_dir)
    
    if not account_dbs:
        print("No account-specific databases found.")
        return 1
    
    print(f"Found {len(account_dbs)} account-specific databases:")
    for device_id, account_name, db_path in account_dbs:
        print(f"  Device: {device_id}, Account: {account_name}, DB: {db_path}")
    
    # Update captions in each account-specific database
    total_updated = 0
    
    for post in dashboard_posts:
        post_id = post['id']
        device_id = post['deviceid']
        account_name = post['account']
        caption = post['caption']
        
        print(f"\nProcessing post {post_id} for Device: {device_id}, Account: {account_name}")
        
        # Find the matching account database
        matching_dbs = [(d, a, db) for d, a, db in account_dbs if d == device_id and a == account_name]
        
        if matching_dbs:
            for _, _, db_path in matching_dbs:
                print(f"Updating caption in database: {db_path}")
                success = update_account_caption(db_path, post_id, caption)
                
                if success:
                    print(f"Successfully updated caption for post {post_id}")
                    print(f"Caption: {caption[:50]}..." if len(caption) > 50 else f"Caption: {caption}")
                    total_updated += 1
                else:
                    print(f"Post {post_id} not found in {db_path}")
        else:
            print(f"No matching account database found for Device: {device_id}, Account: {account_name}")
    
    if total_updated > 0:
        print(f"\nSuccessfully updated {total_updated} posts across account databases")
    else:
        print("\nNo posts were updated in any account database")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
