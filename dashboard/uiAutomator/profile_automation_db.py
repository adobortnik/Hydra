#!/usr/bin/env python3
"""
Database management for Instagram profile automation
Handles profile updates, bio storage, and profile picture tracking
"""

import sqlite3
import os
import datetime
from pathlib import Path

# Database paths
# uiAutomator is now inside the-livehouse-dashboard, device folders are 2 levels up
BASE_DIR = Path(__file__).parent.parent.parent
PROFILE_AUTOMATION_DB = Path(__file__).parent / "profile_automation.db"
PROFILE_PICTURES_DIR = Path(__file__).parent / "profile_pictures"

def init_database():
    """Initialize the profile automation database with all required tables"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    # Table for profile update tasks
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT NOT NULL,
        instagram_package TEXT NOT NULL,
        username TEXT,
        new_username TEXT,
        new_bio TEXT,
        profile_picture_id INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        error_message TEXT,
        ai_api_key TEXT,
        ai_provider TEXT DEFAULT 'openai',
        mother_account TEXT,
        FOREIGN KEY (profile_picture_id) REFERENCES profile_pictures(id)
    )
    ''')

    # Add AI fields to existing tables (if not present)
    try:
        cursor.execute('ALTER TABLE profile_updates ADD COLUMN ai_api_key TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute('ALTER TABLE profile_updates ADD COLUMN ai_provider TEXT DEFAULT "openai"')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('ALTER TABLE profile_updates ADD COLUMN mother_account TEXT')
    except sqlite3.OperationalError:
        pass

    # Table for bio templates
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bio_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        bio_text TEXT NOT NULL,
        category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        times_used INTEGER DEFAULT 0
    )
    ''')

    # Table for profile pictures
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_pictures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        original_path TEXT NOT NULL,
        category TEXT,
        gender TEXT,
        style TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        times_used INTEGER DEFAULT 0,
        last_used TIMESTAMP,
        notes TEXT
    )
    ''')

    # Table for tracking account changes history
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT NOT NULL,
        instagram_package TEXT NOT NULL,
        username TEXT,
        change_type TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success INTEGER DEFAULT 1
    )
    ''')

    # Table for device-account mapping
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS device_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT NOT NULL UNIQUE,
        current_username TEXT,
        current_bio TEXT,
        current_profile_picture_id INTEGER,
        instagram_package TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (current_profile_picture_id) REFERENCES profile_pictures(id)
    )
    ''')

    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_updates_status ON profile_updates(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_updates_device ON profile_updates(device_serial)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_history_device ON profile_history(device_serial)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_device_accounts_serial ON device_accounts(device_serial)')

    conn.commit()
    conn.close()

    # Create profile pictures directory structure
    PROFILE_PICTURES_DIR.mkdir(exist_ok=True)
    (PROFILE_PICTURES_DIR / "male").mkdir(exist_ok=True)
    (PROFILE_PICTURES_DIR / "female").mkdir(exist_ok=True)
    (PROFILE_PICTURES_DIR / "neutral").mkdir(exist_ok=True)
    (PROFILE_PICTURES_DIR / "uploaded").mkdir(exist_ok=True)

    print(f"Database initialized at: {PROFILE_AUTOMATION_DB}")
    print(f"Profile pictures directory: {PROFILE_PICTURES_DIR}")

def add_profile_update_task(device_serial, instagram_package, username=None,
                           new_username=None, new_bio=None, profile_picture_id=None,
                           ai_api_key=None, ai_provider='openai', mother_account=None):
    """
    Add a new profile update task to the queue

    Args:
        device_serial: Device serial number (e.g., "192.168.101.107_5555")
        instagram_package: Instagram package name (e.g., "com.instagram.android")
        username: Current username (optional)
        new_username: New username to set
        new_bio: New bio to set
        profile_picture_id: ID of profile picture from profile_pictures table
        ai_api_key: OpenAI/Anthropic API key for smart username generation
        ai_provider: AI provider (openai or anthropic)
        mother_account: Mother account for AI-based generation

    Returns:
        int: Task ID
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO profile_updates
    (device_serial, instagram_package, username, new_username, new_bio, profile_picture_id,
     ai_api_key, ai_provider, mother_account, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    ''', (device_serial, instagram_package, username, new_username, new_bio, profile_picture_id,
          ai_api_key, ai_provider, mother_account))

    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return task_id

def get_pending_tasks():
    """Get all pending profile update tasks"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
    SELECT pu.*, pp.filename, pp.original_path
    FROM profile_updates pu
    LEFT JOIN profile_pictures pp ON pu.profile_picture_id = pp.id
    WHERE pu.status = 'pending'
    ORDER BY pu.created_at ASC
    ''')

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return tasks

def update_task_status(task_id, status, error_message=None):
    """Update the status of a profile update task"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    if status == 'completed':
        cursor.execute('''
        UPDATE profile_updates
        SET status = ?, updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP, error_message = ?
        WHERE id = ?
        ''', (status, error_message, task_id))
    else:
        cursor.execute('''
        UPDATE profile_updates
        SET status = ?, updated_at = CURRENT_TIMESTAMP, error_message = ?
        WHERE id = ?
        ''', (status, error_message, task_id))

    conn.commit()
    conn.close()

def add_profile_picture(filename, original_path, category=None, gender=None, style=None, notes=None):
    """
    Add a profile picture to the database

    Args:
        filename: Name of the file
        original_path: Original file path
        category: Category (e.g., "professional", "casual", "artistic")
        gender: Gender category ("male", "female", "neutral")
        style: Style description
        notes: Additional notes

    Returns:
        int: Profile picture ID
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO profile_pictures
    (filename, original_path, category, gender, style, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (filename, original_path, category, gender, style, notes))

    pic_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return pic_id

def get_profile_pictures(category=None, gender=None, unused_only=False):
    """
    Get profile pictures from database

    Args:
        category: Filter by category
        gender: Filter by gender
        unused_only: Only return pictures that haven't been used

    Returns:
        list: List of profile picture records
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM profile_pictures WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if gender:
        query += " AND gender = ?"
        params.append(gender)

    if unused_only:
        query += " AND times_used = 0"

    query += " ORDER BY times_used ASC, uploaded_at DESC"

    cursor.execute(query, params)
    pictures = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return pictures

def update_picture_usage(picture_id):
    """Increment usage counter for a profile picture"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE profile_pictures
    SET times_used = times_used + 1, last_used = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (picture_id,))

    conn.commit()
    conn.close()

def add_bio_template(name, bio_text, category=None):
    """
    Add a bio template

    Args:
        name: Template name
        bio_text: Bio text content
        category: Category (e.g., "business", "personal", "influencer")

    Returns:
        int: Bio template ID
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    try:
        cursor.execute('''
        INSERT INTO bio_templates (name, bio_text, category)
        VALUES (?, ?, ?)
        ''', (name, bio_text, category))

        bio_id = cursor.lastrowid
        conn.commit()
        return bio_id
    except sqlite3.IntegrityError:
        print(f"Bio template with name '{name}' already exists")
        return None
    finally:
        conn.close()

def get_bio_templates(category=None):
    """Get bio templates"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if category:
        cursor.execute('SELECT * FROM bio_templates WHERE category = ? ORDER BY times_used ASC', (category,))
    else:
        cursor.execute('SELECT * FROM bio_templates ORDER BY times_used ASC')

    templates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return templates

def update_bio_template_usage(template_id):
    """Increment usage counter for a bio template"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('UPDATE bio_templates SET times_used = times_used + 1 WHERE id = ?', (template_id,))

    conn.commit()
    conn.close()

def log_profile_change(device_serial, instagram_package, username, change_type, old_value, new_value, success=True):
    """
    Log a profile change to history

    Args:
        device_serial: Device serial number
        instagram_package: Instagram package name
        username: Username
        change_type: Type of change ("username", "bio", "profile_picture")
        old_value: Old value
        new_value: New value
        success: Whether the change was successful
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO profile_history
    (device_serial, instagram_package, username, change_type, old_value, new_value, success)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (device_serial, instagram_package, username, change_type, old_value, new_value, int(success)))

    conn.commit()
    conn.close()

def update_device_account(device_serial, username=None, bio=None, profile_picture_id=None, instagram_package=None):
    """Update or create device account record"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM device_accounts WHERE device_serial = ?', (device_serial,))
    exists = cursor.fetchone()

    if exists:
        # Update existing record
        updates = []
        params = []

        if username is not None:
            updates.append("current_username = ?")
            params.append(username)
        if bio is not None:
            updates.append("current_bio = ?")
            params.append(bio)
        if profile_picture_id is not None:
            updates.append("current_profile_picture_id = ?")
            params.append(profile_picture_id)
        if instagram_package is not None:
            updates.append("instagram_package = ?")
            params.append(instagram_package)

        updates.append("last_updated = CURRENT_TIMESTAMP")
        params.append(device_serial)

        query = f"UPDATE device_accounts SET {', '.join(updates)} WHERE device_serial = ?"
        cursor.execute(query, params)
    else:
        # Insert new record
        cursor.execute('''
        INSERT INTO device_accounts
        (device_serial, current_username, current_bio, current_profile_picture_id, instagram_package)
        VALUES (?, ?, ?, ?, ?)
        ''', (device_serial, username, bio, profile_picture_id, instagram_package))

    conn.commit()
    conn.close()

def get_device_account(device_serial):
    """Get device account information"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM device_accounts WHERE device_serial = ?', (device_serial,))
    account = cursor.fetchone()

    conn.close()

    return dict(account) if account else None


def get_all_tasks():
    """Get all profile update tasks (all statuses)"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
    SELECT pu.*, pp.filename, pp.original_path
    FROM profile_updates pu
    LEFT JOIN profile_pictures pp ON pu.profile_picture_id = pp.id
    ORDER BY pu.created_at DESC
    ''')

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return tasks


def get_profile_history(limit=50):
    """Get profile change history"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
    SELECT * FROM profile_history
    ORDER BY changed_at DESC
    LIMIT ?
    ''', (limit,))

    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return history


def delete_task(task_id):
    """Delete a profile update task"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM profile_updates WHERE id = ?', (task_id,))

    conn.commit()
    conn.close()


def clear_old_tasks(days_old=7):
    """Clear completed tasks older than specified days"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('''
    DELETE FROM profile_updates
    WHERE status = 'completed'
    AND completed_at < datetime('now', '-' || ? || ' days')
    ''', (days_old,))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count

def auto_import_profile_pictures():
    """
    Automatically import all images from the 'uploaded' folder into the database

    Scans profile_pictures/uploaded/ for image files and adds any new ones to the database.
    Skips files that are already imported (checks by filename).

    Returns:
        dict: {'imported': int, 'skipped': int, 'total': int}
    """
    upload_dir = PROFILE_PICTURES_DIR / "uploaded"
    upload_dir.mkdir(exist_ok=True)

    # Get list of image files in upload folder
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    image_files = [
        f for f in upload_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ]

    if not image_files:
        print(f"No images found in {upload_dir}")
        return {'imported': 0, 'skipped': 0, 'total': 0}

    # Get existing filenames from database
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT filename FROM profile_pictures')
    existing_filenames = {row[0] for row in cursor.fetchall()}
    conn.close()

    imported = 0
    skipped = 0

    print(f"\nScanning {upload_dir} for images...")
    print(f"Found {len(image_files)} image file(s)")

    for image_file in image_files:
        filename = image_file.name

        if filename in existing_filenames:
            print(f"  - Skipping {filename} (already imported)")
            skipped += 1
            continue

        # Import the image
        try:
            pic_id = add_profile_picture(
                filename=filename,
                original_path=str(image_file.absolute()),
                category='uploaded',
                gender='neutral',  # Default, can be updated later
                notes=f'Auto-imported from uploaded folder'
            )
            print(f"  + Imported {filename} (ID: {pic_id})")
            imported += 1
        except Exception as e:
            print(f"  x Failed to import {filename}: {e}")
            skipped += 1

    print(f"\nImport complete: {imported} new, {skipped} skipped, {len(image_files)} total")

    return {
        'imported': imported,
        'skipped': skipped,
        'total': len(image_files)
    }

if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
    print("Profile automation database initialized successfully!")

    # Auto-import any images in the uploaded folder
    print("\nChecking for new profile pictures...")
    auto_import_profile_pictures()
