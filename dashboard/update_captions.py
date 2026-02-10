#!/usr/bin/env python
# Script to update captions in scheduled posts
# Replaces @christiannreal with @Christian.jagg in all scheduled posts

import os
import sqlite3
import sys

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def update_captions(db_path, old_text, new_text):
    """
    Update all captions in the scheduled_posts table,
    replacing old_text with new_text
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # First, get all posts that contain the old text
        cursor.execute(
            "SELECT id, caption FROM scheduled_posts WHERE caption LIKE ?", 
            (f'%{old_text}%',)
        )
        posts = cursor.fetchall()
        
        if not posts:
            print(f"No posts found containing '{old_text}'")
            conn.close()
            return 0
        
        print(f"Found {len(posts)} posts containing '{old_text}'")
        
        # Update each post
        updated_count = 0
        for post in posts:
            post_id = post['id']
            old_caption = post['caption']
            new_caption = old_caption.replace(old_text, new_text)
            
            cursor.execute(
                "UPDATE scheduled_posts SET caption = ? WHERE id = ?",
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
        print(f"Error updating captions: {e}")
        return -1

def main():
    # Get the absolute path to the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory (which should be the main tool directory)
    # This ensures we're using the same database as both the dashboard and main tool
    base_dir = os.path.dirname(current_dir)
    
    # Path to the scheduled posts database - this is the path shared by both tools
    scheduled_posts_dir = os.path.join(base_dir, 'scheduled_posts')
    db_path = os.path.join(scheduled_posts_dir, 'scheduled_posts.db')
    
    print(f"Using database at: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return 1
    
    old_text = "@christiannreal"
    new_text = "@Christian.jagg"
    
    print(f"Updating captions in {db_path}")
    print(f"Replacing '{old_text}' with '{new_text}'")
    
    updated = update_captions(db_path, old_text, new_text)
    
    if updated > 0:
        print(f"Successfully updated {updated} posts")
        print("This update affects both the dashboard and the main tool since they share the same database.")
    elif updated == 0:
        print("No posts were updated")
    else:
        print("An error occurred during the update")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
