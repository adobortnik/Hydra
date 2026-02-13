# Import necessary modules
import os
import sys
import json
import shutil
import sqlite3
import uuid
import time
import datetime
import re
import random
import string
import hashlib
import subprocess
import traceback
import threading
import requests
import logging
from logging.handlers import RotatingFileHandler
import base64
import io

# ── Crash Logging Setup ──────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# File handler — rotates at 5MB, keeps 3 backups
_file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'dashboard.log'),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8'
)
_file_handler.setLevel(logging.WARNING)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
))

# Apply to root logger so Flask + all modules log to file
logging.basicConfig(level=logging.WARNING, handlers=[_file_handler])
_logger = logging.getLogger('dashboard')
_logger.setLevel(logging.INFO)
_logger.addHandler(_file_handler)

# Catch unhandled exceptions globally
def _uncaught_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    _logger.critical(
        "Unhandled exception — dashboard crashed!",
        exc_info=(exc_type, exc_value, exc_tb)
    )

sys.excepthook = _uncaught_exception_handler
_logger.info("Dashboard starting up (PID: %d)", os.getpid())
import zipfile

# Media folder sync functionality is now in a separate script
from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, make_response, Response
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from jap_api_utils import JAP_API_KEY, save_jap_api_key, load_jap_api_key
from manage_sources import sources_bp
from profile_automation_routes import profile_automation_bp
from settings_routes import settings_bp
from login_automation_routes import login_bp
from bot_manager_routes import bot_manager_bp
from bot_settings_routes import bot_settings_bp
from bulk_import_routes import bulk_import_bp
from job_orders_routes import job_orders_bp
from follow_list_routes import follow_list_bp
from bot_launcher_routes import bot_launcher_bp
from device_management_routes import device_management_bp
from import_v2_routes import import_v2_bp
from login_automation_v2_routes import login_v2_bp
from job_orders_v2_routes import job_orders_v2_bp
from content_schedule_routes import content_schedule_bp
from farm_stats_routes import farm_stats_bp
from account_health_routes import account_health_bp
from proxy_routes import proxy_bp
from device_manager_routes import device_manager_bp
from deploy_routes import deploy_bp
from comment_routes import comment_bp

# Database paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THELIVEHOUSE_DIR = os.path.dirname(os.path.abspath(__file__))
# Keep original paths for media_library and scheduled_posts to sync with main tool
SCHEDULED_POSTS_DIR = os.path.join(BASE_DIR, 'scheduled_posts')
MEDIA_LIBRARY_DIR = os.path.join(BASE_DIR, 'media_library')
# Only account inventory is in thelivehouse directory
ACCOUNT_INVENTORY_DIR = os.path.join(THELIVEHOUSE_DIR, 'data/account_inventory')
ACCOUNT_INVENTORY_DB = os.path.join(ACCOUNT_INVENTORY_DIR, 'account_inventory.db')
DEVICES_DB = os.path.join(BASE_DIR, 'devices.db')
PHONE_FARM_DB = os.path.join(BASE_DIR, 'db', 'phone_farm.db')
# API key storage path
API_KEYS_DIR = os.path.join(THELIVEHOUSE_DIR, 'data/api_keys')
JAP_API_KEY_FILE = os.path.join(API_KEYS_DIR, 'jap_api_key.txt')

# Create directories if they don't exist
os.makedirs(SCHEDULED_POSTS_DIR, exist_ok=True)
os.makedirs(MEDIA_LIBRARY_DIR, exist_ok=True)
os.makedirs(os.path.join(MEDIA_LIBRARY_DIR, 'original'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_LIBRARY_DIR, 'processed'), exist_ok=True)
os.makedirs(ACCOUNT_INVENTORY_DIR, exist_ok=True)
os.makedirs(os.path.dirname(ACCOUNT_INVENTORY_DB), exist_ok=True)  # Ensure DB directory exists
os.makedirs(os.path.join(THELIVEHOUSE_DIR, 'data'), exist_ok=True)
os.makedirs(API_KEYS_DIR, exist_ok=True)

# Helper function to get a database connection
def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to convert row to dict
def row_to_dict(row):
    return {key: row[key] for key in row.keys()} if row else {}

def update_media_usage(media_id):
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        
        cursor.execute('''
        UPDATE media 
        SET times_used = times_used + 1, last_used = ?
        WHERE id = ?
        ''', (now, media_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating media usage: {e}")
        return False

# Folder management functions
def create_media_folder(folder_name, description="", parent_id=None):
    """Create a new folder in the media library"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Generate folder ID
        folder_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        
        # Insert folder
        cursor.execute('''
        INSERT INTO folders (id, name, description, created_at, parent_id)
        VALUES (?, ?, ?, ?, ?)
        ''', (folder_id, folder_name, description, now, parent_id))
        
        conn.commit()
        conn.close()
        return folder_id
    except Exception as e:
        print(f"Error creating folder: {e}")
        return None

def get_all_folders():
    """Get all folders in the media library"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM folders ORDER BY name')
        folders = [row_to_dict(row) for row in cursor.fetchall()]
        
        # Get media count for each folder
        for folder in folders:
            cursor.execute('''
            SELECT COUNT(*) as count FROM media_folders
            WHERE folder_id = ?
            ''', (folder['id'],))
            result = cursor.fetchone()
            folder['media_count'] = result['count'] if result else 0
        
        conn.close()
        return folders
    except Exception as e:
        print(f"Error getting folders: {e}")
        return []

def get_folder(folder_id):
    """Get a specific folder by ID"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM folders WHERE id = ?', (folder_id,))
        folder = row_to_dict(cursor.fetchone())
        
        if folder:
            # Get media count
            cursor.execute('''
            SELECT COUNT(*) as count FROM media_folders
            WHERE folder_id = ?
            ''', (folder_id,))
            result = cursor.fetchone()
            folder['media_count'] = result['count'] if result else 0
            
            # Get child folders
            cursor.execute('SELECT * FROM folders WHERE parent_id = ? ORDER BY name', (folder_id,))
            folder['children'] = [row_to_dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return folder
    except Exception as e:
        print(f"Error getting folder {folder_id}: {e}")
        return None

def update_folder(folder_id, name=None, description=None, parent_id=None):
    """Update a folder's details"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        update_fields = []
        params = []
        
        if name is not None:
            update_fields.append('name = ?')
            params.append(name)
        
        if description is not None:
            update_fields.append('description = ?')
            params.append(description)
        
        if parent_id is not None:
            update_fields.append('parent_id = ?')
            params.append(parent_id)
        
        if not update_fields:
            return True  # Nothing to update
        
        # Add folder_id to params
        params.append(folder_id)
        
        query = f"UPDATE folders SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating folder {folder_id}: {e}")
        return False

def delete_folder(folder_id):
    """Delete a folder and remove all media associations"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if folder has children
        cursor.execute('SELECT COUNT(*) as count FROM folders WHERE parent_id = ?', (folder_id,))
        result = cursor.fetchone()
        if result and result['count'] > 0:
            conn.close()
            return False, "Cannot delete folder with subfolders"
        
        # Remove media associations
        cursor.execute('DELETE FROM media_folders WHERE folder_id = ?', (folder_id,))
        
        # Delete the folder
        cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
        
        conn.commit()
        conn.close()
        return True, "Folder deleted successfully"
    except Exception as e:
        print(f"Error deleting folder {folder_id}: {e}")
        return False, str(e)

def add_media_to_folder(media_id, folder_id):
    """Add a media item to a folder"""
    try:
        print(f"DEBUG: Adding media {media_id} to folder {folder_id}")
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if association already exists
        cursor.execute('SELECT 1 FROM media_folders WHERE media_id = ? AND folder_id = ?', 
                      (media_id, folder_id))
        if cursor.fetchone():
            print(f"DEBUG: Media {media_id} already in folder {folder_id}")
            conn.close()
            return True  # Already associated
        
        # Check if media exists
        cursor.execute('SELECT 1 FROM media WHERE id = ?', (media_id,))
        if not cursor.fetchone():
            print(f"ERROR: Media {media_id} does not exist")
            conn.close()
            return False
        
        # Check if folder exists
        cursor.execute('SELECT 1 FROM folders WHERE id = ?', (folder_id,))
        if not cursor.fetchone():
            print(f"ERROR: Folder {folder_id} does not exist")
            conn.close()
            return False
        
        # Add association
        print(f"DEBUG: Inserting media {media_id} into folder {folder_id}")
        cursor.execute('''
        INSERT INTO media_folders (media_id, folder_id)
        VALUES (?, ?)
        ''', (media_id, folder_id))
        
        conn.commit()
        conn.close()
        print(f"DEBUG: Successfully added media {media_id} to folder {folder_id}")
        return True
    except Exception as e:
        print(f"ERROR adding media {media_id} to folder {folder_id}: {e}")
        traceback.print_exc()
        return False

def remove_media_from_folder(media_id, folder_id):
    """Remove a media item from a folder"""
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM media_folders WHERE media_id = ? AND folder_id = ?', 
                      (media_id, folder_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error removing media {media_id} from folder {folder_id}: {e}")
        return False

def get_media_in_folder(folder_id, tag_filter=None, media_type_filter=None, search_term=None):
    """Get all media items in a specific folder"""
    try:
        print(f"DEBUG: get_media_in_folder called with folder_id={folder_id}, tag_filter={tag_filter}, media_type_filter={media_type_filter}, search_term={search_term}")
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Base query
        query = '''
        SELECT m.* FROM media m
        JOIN media_folders mf ON m.id = mf.media_id
        WHERE mf.folder_id = ?
        '''
        params = [folder_id]
        
        # Add tag filter if specified
        if tag_filter:
            query += ''' 
            AND m.id IN (
                SELECT mt.media_id FROM media_tags mt 
                JOIN tags t ON mt.tag_id = t.id 
                WHERE t.name = ?
            )
            '''
            params.append(tag_filter)
        
        # Add media type filter if specified
        if media_type_filter:
            query += ' AND m.media_type = ?'
            params.append(media_type_filter)
        
        # Add search term filter if specified
        if search_term:
            query += ' AND (m.filename LIKE ? OR m.description LIKE ?)'
            search_param = f'%{search_term}%'
            params.append(search_param)
            params.append(search_param)
        
        # Execute query
        print(f"DEBUG: Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        media_items = [row_to_dict(row) for row in cursor.fetchall()]
        print(f"DEBUG: Query returned {len(media_items)} items")
        
        # Get tags for each media item
        for item in media_items:
            cursor.execute('''
            SELECT t.name FROM tags t
            JOIN media_tags mt ON t.id = mt.tag_id
            WHERE mt.media_id = ?
            ''', (item['id'],))
            tags = [row['name'] for row in cursor.fetchall()]
            item['tags_list'] = tags
        
        conn.close()
        return media_items
    except Exception as e:
        print(f"ERROR getting media in folder {folder_id}: {e}")
        traceback.print_exc()
        return []

# Initialize media library database
def init_media_library_db():
    db_path = os.path.join(MEDIA_LIBRARY_DIR, 'media_library.db')
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create media table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        original_path TEXT NOT NULL,
        processed_path TEXT,
        media_type TEXT NOT NULL,
        file_size INTEGER,
        width INTEGER,
        height INTEGER,
        duration INTEGER,
        tags TEXT,
        description TEXT,
        upload_date TEXT,
        times_used INTEGER DEFAULT 0,
        last_used TEXT
    )
    ''')
    
    # Create tags table for easier filtering
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    ''')
    
    # Create media_tags relationship table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media_tags (
        media_id TEXT,
        tag_id INTEGER,
        PRIMARY KEY (media_id, tag_id),
        FOREIGN KEY (media_id) REFERENCES media(id),
        FOREIGN KEY (tag_id) REFERENCES tags(id)
    )
    ''')
    
    # Create folders table for organizing media
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT,
        parent_id TEXT,
        FOREIGN KEY (parent_id) REFERENCES folders(id)
    )
    ''')
    
    # Create media_folders relationship table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media_folders (
        media_id TEXT,
        folder_id TEXT,
        PRIMARY KEY (media_id, folder_id),
        FOREIGN KEY (media_id) REFERENCES media(id),
        FOREIGN KEY (folder_id) REFERENCES folders(id)
    )
    ''')
    
    # Create content_categories table for automated posting
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS content_categories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        posting_frequency TEXT,
        hashtags TEXT,
        caption_template TEXT,
        created_at TEXT,
        last_used TEXT
    )
    ''')
    
    conn.commit()
    conn.close()
    return db_path

# Get all media from the library
def get_all_media(tag_filter=None, media_type_filter=None, search_term=None):
    try:
        print(f"DEBUG get_all_media: Starting with filters: tag={tag_filter}, type={media_type_filter}, search={search_term}")
        db_path = init_media_library_db()
        print(f"DEBUG get_all_media: Using DB path: {db_path}")
        
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Base query
        query = 'SELECT m.* FROM media m'
        params = []
        
        # Add tag filter if specified
        if tag_filter:
            query += ''' 
            JOIN media_tags mt ON m.id = mt.media_id 
            JOIN tags t ON mt.tag_id = t.id 
            WHERE t.name = ?
            '''
            params.append(tag_filter)
        else:
            query += ' WHERE 1=1'
        
        # Add media type filter if specified
        if media_type_filter:
            query += ' AND m.media_type = ?'
            params.append(media_type_filter)
        
        # Add search term filter if specified
        if search_term:
            query += ' AND (m.filename LIKE ? OR m.description LIKE ?)'
            search_param = f'%{search_term}%'
            params.append(search_param)
            params.append(search_param)
        
        # Execute query
        print(f"DEBUG get_all_media: Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        media_items = [row_to_dict(row) for row in cursor.fetchall()]
        print(f"DEBUG get_all_media: Found {len(media_items)} items")
        
        # Get tags for each media item
        for item in media_items:
            cursor.execute('''
            SELECT t.name FROM tags t
            JOIN media_tags mt ON t.id = mt.tag_id
            WHERE mt.media_id = ?
            ''', (item['id'],))
            tags = [row['name'] for row in cursor.fetchall()]
            item['tags_list'] = tags
            
            # Ensure paths use forward slashes for cross-platform compatibility
            if 'original_path' in item and item['original_path']:
                item['original_path'] = item['original_path'].replace('\\', '/')
            if 'processed_path' in item and item['processed_path']:
                item['processed_path'] = item['processed_path'].replace('\\', '/')
        
        conn.close()
        return media_items
    except Exception as e:
        print(f"ERROR in get_all_media: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

# Get a specific media item
def get_media_item(media_id):
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM media WHERE id = ?', (media_id,))
        media_item = row_to_dict(cursor.fetchone())
        
        if media_item:
            # Get tags for the media item
            cursor.execute('''
            SELECT t.name FROM tags t
            JOIN media_tags mt ON t.id = mt.tag_id
            WHERE mt.media_id = ?
            ''', (media_id,))
            tags = [row['name'] for row in cursor.fetchall()]
            media_item['tags_list'] = tags
        
        conn.close()
        return media_item
    except Exception as e:
        print(f"Error getting media item {media_id}: {e}")
        return None

# Add a new media item to the library
def add_media_to_library(file, description='', tags=None):
    try:
        import PIL.Image
        from PIL import Image, ImageEnhance, ImageFilter
        import hashlib
        
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Generate a unique ID based on file content and timestamp
        file_hash = hashlib.md5(file.read()).hexdigest()
        file.seek(0)  # Reset file pointer after reading
        
        media_id = f"{file_hash}_{int(datetime.datetime.now().timestamp())}"
        now = datetime.datetime.now().isoformat()
        
        # Determine media type based on file extension
        filename = file.filename
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in ['.jpg', '.jpeg', '.png', '.gif']:
            media_type = 'image'
        elif ext in ['.mp4', '.mov', '.avi']:
            media_type = 'video'
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        
        # Save original file
        original_filename = f"{media_id}{ext}"
        # Ensure forward slashes for cross-platform compatibility
        original_path = 'original/' + original_filename
        file_path = os.path.join(MEDIA_LIBRARY_DIR, 'original', original_filename)
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Get dimensions for images
        width = None
        height = None
        duration = None
        
        if media_type == 'image':
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
            except Exception as e:
                print(f"Error getting image dimensions: {e}")
        
        # Insert media record
        cursor.execute('''
        INSERT INTO media 
        (id, filename, original_path, media_type, file_size, width, height, duration, description, upload_date, times_used) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            media_id,
            filename,
            original_path,
            media_type,
            file_size,
            width,
            height,
            duration,
            description,
            now,
            0
        ))
        
        # Process tags
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            
            for tag_name in tag_list:
                # Check if tag exists
                cursor.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
                tag = cursor.fetchone()
                
                if tag:
                    tag_id = tag['id']
                else:
                    # Create new tag
                    cursor.execute('INSERT INTO tags (name) VALUES (?)', (tag_name,))
                    tag_id = cursor.lastrowid
                
                # Link tag to media
                cursor.execute('INSERT INTO media_tags (media_id, tag_id) VALUES (?, ?)', (media_id, tag_id))
        
        conn.commit()
        conn.close()
        
        return media_id
    except Exception as e:
        print(f"Error adding media to library: {e}")
        return None

# Update media item details
def update_media_item(media_id, description=None, tags=None):
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if media exists
        cursor.execute('SELECT * FROM media WHERE id = ?', (media_id,))
        media = cursor.fetchone()
        
        if not media:
            conn.close()
            return False, "Media not found"
        
        # Update description if provided
        if description is not None:
            cursor.execute('UPDATE media SET description = ? WHERE id = ?', (description, media_id))
        
        # Update tags if provided
        if tags is not None:
            # Remove existing tags
            cursor.execute('DELETE FROM media_tags WHERE media_id = ?', (media_id,))
            
            # Add new tags
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            
            for tag_name in tag_list:
                # Check if tag exists
                cursor.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
                tag = cursor.fetchone()
                
                if tag:
                    tag_id = tag['id']
                else:
                    # Create new tag
                    cursor.execute('INSERT INTO tags (name) VALUES (?)', (tag_name,))
                    tag_id = cursor.lastrowid
                
                # Link tag to media
                cursor.execute('INSERT INTO media_tags (media_id, tag_id) VALUES (?, ?)', (media_id, tag_id))
        
        conn.commit()
        conn.close()
        
        return True, "Media updated successfully"
    except Exception as e:
        print(f"Error updating media item {media_id}: {e}")
        return False, str(e)

# Delete a media item
def delete_media_item(media_id):
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Get media paths before deleting
        cursor.execute('SELECT original_path, processed_path FROM media WHERE id = ?', (media_id,))
        media = cursor.fetchone()
        
        if not media:
            conn.close()
            return False, "Media not found"
        
        # Delete the files
        if media['original_path']:
            original_file = os.path.join(MEDIA_LIBRARY_DIR, media['original_path'])
            if os.path.exists(original_file):
                os.remove(original_file)
        
        if media['processed_path']:
            processed_file = os.path.join(MEDIA_LIBRARY_DIR, media['processed_path'])
            if os.path.exists(processed_file):
                os.remove(processed_file)
        
        # Delete from database
        cursor.execute('DELETE FROM media_tags WHERE media_id = ?', (media_id,))
        cursor.execute('DELETE FROM media WHERE id = ?', (media_id,))
        
        conn.commit()
        conn.close()
        
        return True, "Media deleted successfully"
    except Exception as e:
        print(f"Error deleting media item {media_id}: {e}")
        return False, str(e)

# Process an image to avoid detection (metadata removal, slight modifications)
def process_image_for_antidetection(media_id):
    try:
        import PIL.Image
        from PIL import Image, ImageEnhance, ImageFilter
        import piexif
        import random
        
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Get media item
        cursor.execute('SELECT * FROM media WHERE id = ?', (media_id,))
        media = cursor.fetchone()
        
        if not media or media['media_type'] != 'image':
            conn.close()
            return False, "Media not found or not an image"
        
        # Original file path
        original_file = os.path.join(MEDIA_LIBRARY_DIR, media['original_path'])
        if not os.path.exists(original_file):
            conn.close()
            return False, "Original file not found"
        
        # Create processed filename
        ext = os.path.splitext(media['filename'])[1].lower()
        processed_filename = f"{media_id}_processed{ext}"
        processed_path = os.path.join('processed', processed_filename)
        processed_file = os.path.join(MEDIA_LIBRARY_DIR, processed_path)
        
        # Open the image
        img = Image.open(original_file)
        
        # Apply subtle modifications
        # 1. Slight crop and resize back to original dimensions
        width, height = img.size
        crop_pixels = random.randint(1, 5)  # Random crop between 1-5 pixels
        img = img.crop((crop_pixels, crop_pixels, width-crop_pixels, height-crop_pixels))
        img = img.resize((width, height), Image.LANCZOS)
        
        # 2. Slight adjustment to brightness/contrast/saturation
        enhancer = ImageEnhance.Brightness(img)
        factor = random.uniform(0.98, 1.02)  # Random brightness adjustment ±2%
        img = enhancer.enhance(factor)
        
        enhancer = ImageEnhance.Contrast(img)
        factor = random.uniform(0.98, 1.02)  # Random contrast adjustment ±2%
        img = enhancer.enhance(factor)
        
        # 3. Add imperceptible noise
        img = img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=10, threshold=0))
        
        # Save the processed image without metadata
        img.save(processed_file)
        
        # Update database with processed path
        cursor.execute('UPDATE media SET processed_path = ? WHERE id = ?', (processed_path, media_id))
        conn.commit()
        conn.close()
        
        return True, "Image processed successfully"
    except Exception as e:
        print(f"Error processing image {media_id}: {e}")
        return False, str(e)

# Initialize account inventory database
def init_account_inventory_db():
    # Ensure the directory exists
    os.makedirs(os.path.dirname(ACCOUNT_INVENTORY_DB), exist_ok=True)
    
    # Use the global database path
    db_path = ACCOUNT_INVENTORY_DB
    
    print(f"Using account inventory database at: {db_path}")
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create account inventory table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS account_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        two_factor_auth TEXT,
        status TEXT DEFAULT 'available',
        device_assigned TEXT,
        date_added TEXT,
        date_used TEXT,
        notes TEXT,
        appid TEXT DEFAULT 'com.instagram.android'
    )
    ''')
    
    # Add appid column if it doesn't exist
    try:
        cursor.execute("SELECT appid FROM account_inventory LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        cursor.execute("ALTER TABLE account_inventory ADD COLUMN appid TEXT DEFAULT 'com.instagram.android'")
        conn.commit()
    
    conn.commit()
    conn.close()
    
    return db_path

# Get all accounts from inventory
def get_inventory_accounts():
    """
    Get all accounts from the inventory
    """
    try:
        db_path = init_account_inventory_db()
        print(f"Using database path: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM account_inventory ORDER BY date_added DESC")
        accounts = [dict(row) for row in cursor.fetchall()]
        
        # Debug: Print account IDs
        print(f"Loaded {len(accounts)} accounts from database")
        if accounts:
            print(f"Account IDs: {[account['id'] for account in accounts]}")
        
        return accounts
    except Exception as e:
        print(f"Error getting inventory accounts: {e}")
        return []
    finally:
        if conn:
            conn.close()

# Get a single account from the inventory by ID
def get_inventory_account(account_id):
    """
    Get a single account from the inventory by ID
    """
    try:
        db_path = init_account_inventory_db()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM account_inventory WHERE id = ?", (account_id,))
        account = cursor.fetchone()
        
        if account:
            return dict(account)
        return None
    except Exception as e:
        print(f"Error getting inventory account: {e}")
        return None
    finally:
        if conn:
            conn.close()

# Add accounts to inventory
def add_accounts_to_inventory(accounts_data):
    try:
        print(f"Adding {len(accounts_data)} accounts to inventory")
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        added_count = 0
        skipped_count = 0
        
        for account in accounts_data:
            username = account.get('username')
            password = account.get('password')
            two_factor_auth = account.get('two_factor_auth', '')
            appid = account.get('appid', 'com.instagram.android')
            
            if not username or not password:
                skipped_count += 1
                continue
            
            # Check if account already exists
            cursor.execute('SELECT * FROM account_inventory WHERE username = ?', (username,))
            existing_account = cursor.fetchone()
            
            if existing_account:
                skipped_count += 1
                continue
            
            # Add account to inventory
            now = datetime.datetime.now().isoformat()
            cursor.execute('''
            INSERT INTO account_inventory 
            (username, password, two_factor_auth, status, date_added, appid) 
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, password, two_factor_auth, 'available', now, appid))
            
            added_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"Successfully added {added_count} accounts, skipped {skipped_count} duplicates")
        return added_count, skipped_count
    except Exception as e:
        print(f"Error adding accounts to inventory: {e}")
        return False, str(e)

# Parse accounts from text format
def parse_accounts_from_text(accounts_text):
    accounts = []
    lines = accounts_text.strip().split('\n')
    
    for line in lines:
        if not line.strip():
            continue
        
        parts = line.strip().split(':')
        
        if len(parts) >= 2:  # At minimum, we need username and password
            account = {
                'username': parts[0].strip(),
                'password': parts[1].strip(),
                'two_factor_auth': parts[2].strip() if len(parts) > 2 and parts[2].strip() else '',
                'appid': parts[3].strip() if len(parts) > 3 and parts[3].strip() else 'com.instagram.android'
            }
            accounts.append(account)
    
    return accounts

# Update account in inventory
def update_inventory_account(account_id, account_data):
    """
    Update an account in the inventory
    """
    try:
        conn = sqlite3.connect(ACCOUNT_INVENTORY_DB)
        cursor = conn.cursor()
        
        # Build the update query dynamically based on the provided data
        update_fields = []
        update_values = []
        
        for key, value in account_data.items():
            if key != 'id':  # Skip the ID field
                update_fields.append(f"{key} = ?")
                update_values.append(value)
        
        if not update_fields:
            return False
        
        # Add the account ID to the values
        update_values.append(account_id)
        
        # Execute the update query
        query = f"UPDATE account_inventory SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, update_values)
        conn.commit()
        
        return True
    except Exception as e:
        print(f"Error updating inventory account: {e}")
        return False
    finally:
        if conn:
            conn.close()

# Mark account as used and assign to device
def assign_account_to_device(account_id, device_id):
    try:
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if account exists and is available
        cursor.execute('SELECT * FROM account_inventory WHERE id = ?', (account_id,))
        account = cursor.fetchone()
        
        if not account:
            conn.close()
            return False, "Account not found"
        
        if account['status'] != 'available':
            conn.close()
            return False, "Account is not available"
        
        # Update account status
        now = datetime.datetime.now().isoformat()
        cursor.execute('''
        UPDATE account_inventory 
        SET status = ?, device_assigned = ?, date_used = ? 
        WHERE id = ?
        ''', ('used', device_id, now, account_id))
        
        conn.commit()
        
        # Get account details for adding to device
        username = account['username']
        password = account['password']
        appid = account.get('appid', 'com.instagram.android')  # Get appid or use default
        
        # Add account to device
        accounts_db_path = os.path.join(BASE_DIR, device_id, 'accounts.db')
        
        if not os.path.exists(os.path.dirname(accounts_db_path)):
            conn.close()
            return False, f"Device directory {device_id} does not exist"
        
        accounts_conn = get_db_connection(accounts_db_path)
        accounts_cursor = accounts_conn.cursor()
        
        # Check if account already exists in device
        accounts_cursor.execute('SELECT * FROM accounts WHERE account = ?', (username,))
        existing_account = accounts_cursor.fetchone()
        
        if existing_account:
            accounts_conn.close()
            conn.close()
            return False, "Account already exists in device"
        
        # Create accounts table if it doesn't exist with exact fields from the main tool
        accounts_cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            starttime text,
            endtime text,
            account text NOT NULL,
            password text NOT NULL,
            follow text,
            unfollow text,
            mute text,
            like text,
            comment text,
            story text,
            followmethod text,
            unfollowmethod text,
            unfollowafter text,
            firstaction text,
            secondaction text,
            thirdaction text,
            followsource text,
            unfollowsource text,
            likesource text,
            muteaction text,
            followaction text,
            unfollowaction text,
            likeaction text,
            randomaction text,
            randomdelay text,
            switchmode text,
            followdelay text,
            unfollowdelay text,
            likedelay text,
            followlimitperday text,
            unfollowlimitperday text,
            likelimitperday text,
            limitperday text,
            unfollowdelayday text,
            mutemethod text
        )
        ''')
        
        # Insert account with all fields from the main tool
        accounts_cursor.execute('''
        INSERT INTO accounts (
            starttime, endtime, account, password, follow, unfollow, mute, like,
            comment, story, followmethod, unfollowmethod, unfollowafter, firstaction, secondaction, thirdaction,
            followsource, unfollowsource, likesource, muteaction, followaction, unfollowaction,
            likeaction, randomaction, randomdelay, switchmode, followdelay, 
            unfollowdelay, likedelay, followlimitperday, unfollowlimitperday, 
            likelimitperday, unfollowdelayday, mutemethod
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            '0', '0', username, password, 'Off', 'Off', 'Off', 'Off',
            'Off', 'Off', 'hashtag', 'all', '50', 'follow', 'unfollow', 'like',
            'explore', 'database', 'explore', 'Off', 'Off', 'Off',
            'Off', 'Off', '0', '30', '30', '30', '0', '0', '0', '0', 'Off'
        ))
        
        accounts_conn.commit()
        accounts_conn.close()
        
        # Create account directory inside the device folder
        account_dir = os.path.join(BASE_DIR, device_id, username)
        os.makedirs(account_dir, exist_ok=True)
        
        # Create all the necessary database files
        db_files = [
            '2factorauthcodes.db',
            'comments.db',
            'data.db',
            'directmessage.db',
            'filtersettings.db',
            'likeexchange.db',
            'likes.db',
            'messages.db',
            'scheduled_post.db',
            'sent_message.db',
            'settings.db',
            'stats.db',
            'storyviewer.db'
        ]
        
        for db_file in db_files:
            db_path = os.path.join(account_dir, db_file)
            if not os.path.exists(db_path):
                # Create an empty database file
                db_conn = get_db_connection(db_path)
                db_conn.commit()
                db_conn.close()
        
        # Create the stats.db with proper structure
        stats_db_path = os.path.join(account_dir, 'stats.db')
        stats_conn = get_db_connection(stats_db_path)
        stats_cursor = stats_conn.cursor()
        
        # Create stats table with the exact structure from the main tool
        stats_cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            account text,
            posts text,
            followers text,
            following text,
            date text
        )
        ''')
        
        # Insert initial stats
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        stats_cursor.execute('''
        INSERT INTO stats (account, posts, followers, following, date)
        VALUES (?, ?, ?, ?, ?)
        ''', (username, '0', '0', '0', today))
        
        stats_conn.commit()
        stats_conn.close()
        
        # Create settings.db with proper structure and default settings
        settings_db_path = os.path.join(account_dir, 'settings.db')
        settings_conn = get_db_connection(settings_db_path)
        settings_cursor = settings_conn.cursor()
        
        # Create accountsettings table
        settings_cursor.execute('''
        CREATE TABLE IF NOT EXISTS accountsettings (
            id INTEGER NOT NULL, 
            settings VARCHAR, 
            PRIMARY KEY (id)
        )
        ''')
        
        # Default settings JSON (based on existing accounts)
        default_settings = json.dumps({
            "add_close_friend_limit_perday": "None",
            "app_cloner": "None",
            "auto_increment_action_limit_by": "20",
            "comment_limit_perday": 25,
            "comment_max_delay": 10,
            "comment_method": {"comment_using_keyword_search": False},
            "comment_min_delay": 5,
            "comment_text": "[AI]",
            "default_action_limit_perday": "60",
            "delete_savedpost_source": False,
            "directmessage_daily_limit": "25",
            "directmessage_max": "5",
            "directmessage_method": {"directmessage_new_followers": False},
            "directmessage_min_delay": "10",
            "directmessage_text": "[AI]",
            "follow_limit_perday": "50",
            "follow_max_delay": "30",
            "follow_method": {"follow_hashtag": True},
            "follow_min_delay": "15",
            "like_limit_perday": "50",
            "like_max_delay": "30",
            "like_method": {"like_hashtag": True},
            "like_min_delay": "15",
            "mute_method": {"mute_all": True},
            "random_action": "30,60",
            "random_delay": "30,60",
            "saved_post_limit_perday": "25",
            "saved_post_max_delay": "10",
            "saved_post_min_delay": "5",
            "storyviewer_limit_perday": "100",
            "storyviewer_max_delay": "10",
            "storyviewer_method": {"storyviewer_hashtag": True},
            "storyviewer_min_delay": "5",
            "switch_mode": "off",
            "unfollow_delay_day": "3",
            "unfollow_limit_perday": "50",
            "unfollow_max_delay": "30",
            "unfollow_method": {"unfollow_all": True},
            "unfollow_min_delay": "15"
        })
        
        # Insert default settings
        settings_cursor.execute('INSERT OR REPLACE INTO accountsettings (id, settings) VALUES (?, ?)', (1, default_settings))
        
        settings_conn.commit()
        settings_conn.close()
        
        conn.close()
        return True, "Account successfully assigned to device"
    except Exception as e:
        print(f"Error assigning account to device: {e}")
        return False, str(e)

# Delete account from inventory
def delete_inventory_account(account_id):
    try:
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if account exists
        cursor.execute('SELECT * FROM account_inventory WHERE id = ?', (account_id,))
        account = cursor.fetchone()
        
        if not account:
            conn.close()
            return False, "Account not found"
        
        # Delete account
        cursor.execute('DELETE FROM account_inventory WHERE id = ?', (account_id,))
        
        conn.commit()
        conn.close()
        
        return True, "Account deleted successfully"
    except Exception as e:
        print(f"Error deleting inventory account {account_id}: {e}")
        return False, str(e)

# Delete account from device
def remove_account_from_device(device_id, username):
    try:
        # Check if device exists
        device_dir = os.path.join(BASE_DIR, device_id)
        if not os.path.exists(device_dir):
            return False, f"Device {device_id} not found"
        
        # Check if account exists in accounts.db
        accounts_db_path = os.path.join(device_dir, 'accounts.db')
        if not os.path.exists(accounts_db_path):
            return False, f"Accounts database not found for device {device_id}"
        
        accounts_conn = get_db_connection(accounts_db_path)
        accounts_cursor = accounts_conn.cursor()
        
        # Check if account exists
        accounts_cursor.execute('SELECT * FROM accounts WHERE account = ?', (username,))
        account = accounts_cursor.fetchone()
        
        if not account:
            accounts_conn.close()
            return False, f"Account {username} not found in device {device_id}"
        
        # Delete account from accounts.db
        accounts_cursor.execute('DELETE FROM accounts WHERE account = ?', (username,))
        accounts_conn.commit()
        accounts_conn.close()
        
        # Delete account directory
        account_dir = os.path.join(device_dir, username)
        if os.path.exists(account_dir):
            shutil.rmtree(account_dir)
        
        # Update account status in inventory if it exists
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Find account by username and device
        cursor.execute('SELECT * FROM account_inventory WHERE username = ? AND device_assigned = ?', (username, device_id))
        inventory_account = cursor.fetchone()
        
        if inventory_account:
            # Update account status to available
            cursor.execute('''
            UPDATE account_inventory 
            SET status = ?, device_assigned = ?, date_used = ? 
            WHERE id = ?
            ''', ('available', '', '', inventory_account['id']))
            conn.commit()
        
        conn.close()
        
        return True, f"Account {username} successfully removed from device {device_id}"
    except Exception as e:
        print(f"Error removing account from device: {e}")
        return False, str(e)

# JustAnotherPanel API integration
JAP_API_URL = 'https://justanotherpanel.com/api/v2'
JAP_API_KEY = ''

# Load JAP API key from file at startup
try:
    if os.path.exists(JAP_API_KEY_FILE):
        with open(JAP_API_KEY_FILE, 'r') as f:
            JAP_API_KEY = f.read().strip()
            print(f"Loaded JAP API key from file: {JAP_API_KEY[:5]}...")
except Exception as e:
    print(f"Error loading JAP API key at startup: {e}")

# Function to save API key to file
def save_jap_api_key(api_key):
    """
    Save the JustAnotherPanel API key to a file
    """
    try:
        with open(JAP_API_KEY_FILE, 'w') as f:
            f.write(api_key)
        return True
    except Exception as e:
        print(f"Error saving API key: {e}")
        return False

# Function to load API key from file
def load_jap_api_key():
    """
    Load the JustAnotherPanel API key from a file
    """
    global JAP_API_KEY
    try:
        if os.path.exists(JAP_API_KEY_FILE):
            with open(JAP_API_KEY_FILE, 'r') as f:
                JAP_API_KEY = f.read().strip()
            return JAP_API_KEY
        return ''
    except Exception as e:
        print(f"Error loading API key: {e}")
        return ''

# Load API key on startup
JAP_API_KEY = load_jap_api_key()

def get_jap_services():
    """
    Get the list of services from JustAnotherPanel API
    """
    try:
        payload = {
            'key': JAP_API_KEY,
            'action': 'services'
        }
        
        response = requests.post(JAP_API_URL, data=payload)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        
        return response.json()
    except Exception as e:
        print(f"Error getting JAP services: {e}")
        return []

def order_instagram_followers(username, quantity, service_id=None):
    """
    Order Instagram followers for a specific username
    """
    try:
        if not JAP_API_KEY:
            return {'error': 'API key not configured'}
            
        # If no service_id is provided, use a default one
        if not service_id:
            # You should replace this with your preferred service ID from the services list
            service_id = 1  # Default service ID for followers
        
        # Construct the Instagram profile URL
        instagram_url = f"https://instagram.com/{username}"
        
        payload = {
            'key': JAP_API_KEY,
            'action': 'add',
            'service': service_id,
            'link': instagram_url,
            'quantity': quantity
        }
        
        response = requests.post(JAP_API_URL, data=payload)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        
        result = response.json()
        
        # Store the order in our database for tracking
        store_follower_order(username, quantity, service_id, result.get('order'))
        
        return result
    except Exception as e:
        print(f"Error ordering Instagram followers: {e}")
        return {'error': str(e)}

def check_order_status(order_id):
    """
    Check the status of a specific order
    """
    try:
        payload = {
            'key': JAP_API_KEY,
            'action': 'status',
            'order': order_id
        }
        
        response = requests.post(JAP_API_URL, data=payload)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        
        return response.json()
    except Exception as e:
        print(f"Error checking order status: {e}")
        return {'error': str(e)}

def init_follower_orders_db():
    """
    Initialize the database for tracking follower orders
    """
    try:
        db_path = os.path.join(BASE_DIR, 'follower_orders.db')
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS follower_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
        
        return db_path
    except Exception as e:
        print(f"Error initializing follower orders database: {e}")
        return None

def store_follower_order(username, quantity, service_id, order_id):
    """
    Store a follower order in the database
    """
    try:
        db_path = init_follower_orders_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        
        cursor.execute('''
        INSERT INTO follower_orders 
        (username, quantity, service_id, order_id, created_at, updated_at) 
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, quantity, service_id, order_id, now, now))
        
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error storing follower order: {e}")
        return False

def get_follower_orders(username=None):
    """
    Get all follower orders or orders for a specific username
    """
    try:
        db_path = init_follower_orders_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        if username:
            cursor.execute('SELECT * FROM follower_orders WHERE username = ? ORDER BY created_at DESC', (username,))
        else:
            cursor.execute('SELECT * FROM follower_orders ORDER BY created_at DESC')
            
        orders = [row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return orders
    except Exception as e:
        print(f"Error getting follower orders: {e}")
        return []

def update_order_status(order_id, status):
    """
    Update the status of an order in the database
    """
    try:
        db_path = init_follower_orders_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        
        cursor.execute('''
        UPDATE follower_orders 
        SET status = ?, updated_at = ? 
        WHERE order_id = ?
        ''', (status, now, order_id))
        
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error updating order status: {e}")
        return False

# Get all devices
def get_devices():
    # Try old Onimator devices.db first
    try:
        conn = get_db_connection(DEVICES_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices')
        devices = [row_to_dict(row) for row in cursor.fetchall()]
        conn.close()

        if devices:
            # Add accounts count for each device
            for device in devices:
                device_id = device.get('deviceid')
                if device_id:
                    accounts_db_path = os.path.join(BASE_DIR, device_id, 'accounts.db')
                    if os.path.exists(accounts_db_path):
                        try:
                            acc_conn = get_db_connection(accounts_db_path)
                            acc_cursor = acc_conn.cursor()
                            acc_cursor.execute('SELECT COUNT(*) FROM accounts')
                            count = acc_cursor.fetchone()[0]
                            acc_conn.close()
                            device['accounts_count'] = count
                        except:
                            device['accounts_count'] = 0
                    else:
                        device['accounts_count'] = 0
            return devices
    except Exception as e:
        pass  # Old devices.db not available, fall through to phone_farm.db

    # Fallback: read from phone_farm.db (central DB)
    try:
        conn = get_db_connection(PHONE_FARM_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.id, d.device_serial, d.device_name, d.ip_address, d.status,
                   COUNT(a.id) as accounts_count
            FROM devices d
            LEFT JOIN accounts a ON a.device_id = d.id
            GROUP BY d.id
            ORDER BY d.device_name
        ''')
        rows = cursor.fetchall()
        conn.close()

        devices = []
        for row in rows:
            devices.append({
                'deviceid': row['device_serial'],
                'devicename': row['device_name'],
                'ip_address': row['ip_address'],
                'status': row['status'] or 'active',
                'accounts_count': row['accounts_count'],
                '_source': 'phone_farm_db'
            })
        return devices
    except Exception as e:
        print(f"Error getting devices from phone_farm.db: {e}")
        return []

# Get accounts for a device
def get_accounts(deviceid):
    # Try old Onimator per-device accounts.db first
    try:
        accounts_db_path = os.path.join(BASE_DIR, deviceid, 'accounts.db')
        if os.path.exists(accounts_db_path):
            conn = get_db_connection(accounts_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(accounts)")
            columns = [row[1] for row in cursor.fetchall()]
            cursor.execute('SELECT * FROM accounts')
            accounts_raw = cursor.fetchall()
            conn.close()

            if accounts_raw:
                accounts = []
                for account_raw in accounts_raw:
                    account = dict(account_raw)
                    essential_fields = {
                        'starttime': '0', 'endtime': '0',
                        'follow': 'Off', 'unfollow': 'Off', 'like': 'Off',
                        'comment': 'Off', 'story': 'Off', 'mute': 'Off',
                        'random': 'Off', 'followlimit': '50'
                    }
                    for field, default_value in essential_fields.items():
                        if field not in account or account[field] is None:
                            account[field] = default_value
                    accounts.append(account)
                return accounts
    except Exception as e:
        print(f"Old accounts.db not available for {deviceid}: {e}")

    # Fallback: read from phone_farm.db
    try:
        conn = get_db_connection(PHONE_FARM_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT a.*, d.device_name
            FROM accounts a
            JOIN devices d ON a.device_id = d.id
            WHERE a.device_serial = ?
            ORDER BY a.username
        ''', (deviceid,))
        rows = cursor.fetchall()
        conn.close()

        accounts = []
        for row in rows:
            r = dict(row)
            accounts.append({
                'account': r.get('username', ''),
                'password': r.get('password', ''),
                'email': r.get('email', ''),
                'instagram_package': r.get('instagram_package', ''),
                'deviceid': r.get('device_serial', deviceid),
                'devicename': r.get('device_name', ''),
                'starttime': r.get('start_time', '0') or '0',
                'endtime': r.get('end_time', '0') or '0',
                'follow': 'On' if r.get('follow_enabled') else 'Off',
                'unfollow': 'On' if r.get('unfollow_enabled') else 'Off',
                'like': 'On' if r.get('like_enabled') else 'Off',
                'comment': 'On' if r.get('comment_enabled') else 'Off',
                'story': 'On' if r.get('story_enabled') else 'Off',
                'mute': 'On' if r.get('mute_enabled') else 'Off',
                'random': 'Off',
                'switchmode': r.get('switchmode', ''),
                'followaction': r.get('follow_action', ''),
                'unfollowaction': r.get('unfollow_action', ''),
                'randomaction': r.get('random_action', ''),
                'randomdelay': r.get('random_delay', ''),
                'followdelay': r.get('follow_delay', ''),
                'unfollowdelay': r.get('unfollow_delay', ''),
                'likedelay': r.get('like_delay', ''),
                'followlimitperday': r.get('follow_limit_perday', '50'),
                'unfollowlimitperday': r.get('unfollow_limit_perday', '50'),
                'likelimitperday': r.get('like_limit_perday', '50'),
                'unfollowdelayday': r.get('unfollow_delay_day', ''),
                'followlimit': r.get('follow_limit_perday', '50') or '50',
                '_source': 'phone_farm_db'
            })
        return accounts
    except Exception as e:
        print(f"Error getting accounts for device {deviceid} from phone_farm.db: {e}")
        return []

# Get stats for an account
def get_account_stats(deviceid, account):
    try:
        stats_db_path = os.path.join(BASE_DIR, deviceid, account, 'stats.db')
        if not os.path.exists(stats_db_path):
            # Return empty stats dictionary with default values
            return {
                'followers': '0',
                'following': '0',
                'posts': '0',
                'likes': '0',
                'comments': '0'
            }
            
        conn = get_db_connection(stats_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stats ORDER BY date DESC LIMIT 1')
        stats = cursor.fetchone()
        conn.close()
        
        if stats:
            return dict(stats)
        
        # Return empty stats dictionary with default values if no stats found
        return {
            'followers': '0',
            'following': '0',
            'posts': '0',
            'likes': '0',
            'comments': '0'
        }
    except Exception as e:
        print(f"Error getting stats for account {account} on device {deviceid}: {e}")
        # Return empty stats dictionary with default values on error
        return {
            'followers': '0',
            'following': '0',
            'posts': '0',
            'likes': '0',
            'comments': '0'
        }

# Update account settings
def update_account_settings(deviceid, account_name, settings):
    try:
        accounts_db_path = os.path.join(BASE_DIR, deviceid, 'accounts.db')
        if not os.path.exists(accounts_db_path):
            return False, "Device not found"
        
        conn = get_db_connection(accounts_db_path)
        cursor = conn.cursor()
        
        # Check if account exists
        cursor.execute('SELECT * FROM accounts WHERE account = ?', (account_name,))
        existing = cursor.fetchone()
        
        if not existing:
            conn.close()
            return False, "Account not found"
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in settings.items():
            if key in ['password', 'starttime', 'endtime', 'follow', 'unfollow', 'like', 'comment', 'story', 'mute',
                      'followmethod', 'unfollowmethod', 'mutemethod', 'followaction', 'unfollowaction',
                      'likeaction', 'followdelay', 'unfollowdelay', 'likedelay', 'randomdelay', 'randomaction',
                      'followlimitperday', 'unfollowlimitperday', 'likelimitperday', 'limitperday',
                      'unfollowdelayday', 'switchmode']:
                set_clauses.append(f"{key} = ?")
                params.append(value)
        
        if not set_clauses:
            conn.close()
            return False, "No valid settings to update"
        
        # Add account_name to params
        params.append(account_name)
        
        # Execute update
        query = f"UPDATE accounts SET {', '.join(set_clauses)} WHERE account = ?"
        cursor.execute(query, params)
        
        conn.commit()
        conn.close()
        
        return True, "Account settings updated successfully"
    except Exception as e:
        print(f"Error updating account settings: {e}")
        return False, str(e)

# Get all accounts from all devices
def get_all_accounts():
    devices = get_devices()
    all_accounts = []
    
    for device in devices:
        deviceid = device['deviceid']
        accounts = get_accounts(deviceid)
        
        for account in accounts:
            account_data = dict(account)
            account_data['deviceid'] = deviceid
            account_data['devicename'] = device.get('devicename', deviceid)
            
            # Get account stats
            stats = get_account_stats(deviceid, account['account'])
            account_data['stats'] = stats
            
            all_accounts.append(account_data)
    
    return all_accounts

# Get dashboard statistics
def get_dashboard_stats():
    devices = get_devices()
    all_accounts = get_all_accounts()
    
    # Calculate statistics
    total_devices = len(devices)
    total_accounts = len(all_accounts)
    
    active_accounts = 0
    total_followers = 0
    total_following = 0
    
    for account in all_accounts:
        # Check if account is active (has starttime)
        if account.get('starttime') and account.get('starttime') != '0':
            active_accounts += 1
        
        # Sum followers and following
        if account.get('stats'):
            followers = account.get('stats', {}).get('followers')
            following = account.get('stats', {}).get('following')
            
            if followers and followers.isdigit():
                total_followers += int(followers)
            
            if following and following.isdigit():
                total_following += int(following)
    
    # Get accounts by follow status
    follow_enabled = sum(1 for account in all_accounts if account.get('follow') == 'True')
    unfollow_enabled = sum(1 for account in all_accounts if account.get('unfollow') == 'True')
    
    # Get accounts by device
    accounts_by_device = {}
    for device in devices:
        device_id = device['deviceid']
        device_name = device['devicename']
        count = sum(1 for account in all_accounts if account.get('deviceid') == device_id)
        accounts_by_device[device_id] = {
            'name': device_name,
            'count': count
        }
    
    return {
        'total_devices': total_devices,
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'total_followers': total_followers,
        'total_following': total_following,
        'follow_enabled': follow_enabled,
        'unfollow_enabled': unfollow_enabled,
        'accounts_by_device': accounts_by_device
    }

# Initialize scheduled posts database
def init_scheduled_posts_db():
    db_path = os.path.join(SCHEDULED_POSTS_DIR, 'scheduled_posts.db')
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create scheduled posts table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scheduled_posts (
        id TEXT PRIMARY KEY,
        deviceid TEXT NOT NULL,
        account TEXT NOT NULL,
        post_type TEXT NOT NULL,
        caption TEXT,
        media_path TEXT,
        location TEXT,
        scheduled_time TEXT NOT NULL,
        status TEXT DEFAULT 'scheduled',
        created_at TEXT,
        updated_at TEXT
    )
    ''')
    
    conn.commit()
    conn.close()
    return db_path

# Get all scheduled posts
def get_scheduled_posts():
    try:
        db_path = init_scheduled_posts_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM scheduled_posts ORDER BY scheduled_time ASC')
        posts = [row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return posts
    except Exception as e:
        print(f"Error getting scheduled posts: {e}")
        return []

# Get a specific scheduled post
def get_scheduled_post(post_id):
    try:
        db_path = init_scheduled_posts_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM scheduled_posts WHERE id = ?', (post_id,))
        post = row_to_dict(cursor.fetchone())
        conn.close()
        return post
    except Exception as e:
        print(f"Error getting scheduled post {post_id}: {e}")
        return None

# Create a new scheduled post
def create_scheduled_post(post_data):
    try:
        # Create post in central database
        db_path = init_scheduled_posts_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        post_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        
        # Handle media file if provided
        media_path = None
        if post_data.get('media'):
            # Save media file
            media_dir = os.path.join(SCHEDULED_POSTS_DIR, 'media')
            os.makedirs(media_dir, exist_ok=True)
            
            media_file = post_data['media']
            filename = f"{post_id}_{media_file.filename}"
            media_path = os.path.join('media', filename)
            media_file_path = os.path.join(SCHEDULED_POSTS_DIR, media_path)
            
            # Check if media_file is a BytesIO object or a FileStorage object
            if hasattr(media_file, 'save'):
                # It's a FileStorage object (from Flask uploads)
                media_file.save(media_file_path)
            else:
                # It's a BytesIO object
                with open(media_file_path, 'wb') as f:
                    f.write(media_file.getvalue())
                print(f"Saved media file to {media_file_path}")
        
        # Insert post data into central database
        print(f"Saving post with caption: {post_data.get('caption', '')}")
        cursor.execute('''
        INSERT INTO scheduled_posts 
        (id, deviceid, account, post_type, caption, media_path, location, scheduled_time, status, created_at, updated_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_id,
            post_data['deviceid'],
            post_data['account'] if isinstance(post_data['account'], str) else post_data['account']['account'],
            post_data['post_type'],
            post_data.get('caption', ''),
            media_path,
            post_data.get('location', ''),
            post_data['scheduled_time'],
            'scheduled',
            now,
            now
        ))
        
        conn.commit()
        conn.close()
        
        # Now also write to account-specific database for main tool compatibility
        device_id = post_data['deviceid']
        account_name = post_data['account'] if isinstance(post_data['account'], str) else post_data['account']['account']
        
        # Construct path to account's scheduled_post.db
        account_dir = os.path.join(BASE_DIR, device_id, account_name)
        
        # Check if the account directory exists
        if os.path.exists(account_dir):
            account_db_path = os.path.join(account_dir, 'scheduled_post.db')
            
            # Copy media file to account's directory if needed
            account_media_path = None
            if media_path:
                # Create media directory if it doesn't exist
                account_media_dir = os.path.join(account_dir, 'media')
                print(f"DEBUG: Account directory: {account_dir}")
                print(f"DEBUG: Account media directory: {account_media_dir}")
                print(f"DEBUG: Account media directory exists before makedirs: {os.path.exists(account_media_dir)}")
                os.makedirs(account_media_dir, exist_ok=True)
                print(f"DEBUG: Account media directory exists after makedirs: {os.path.exists(account_media_dir)}")
                
                # Copy the media file
                source_media = os.path.join(SCHEDULED_POSTS_DIR, media_path)
                
                # Create a timestamp-based filename similar to the working example (1745290191.213536.mp4)
                # Format the timestamp with a decimal point to match the existing format
                timestamp = time.time()  # Get current time as float
                timestamp_str = f"{timestamp:.6f}".replace('.', '.')
                file_extension = os.path.splitext(os.path.basename(media_path))[1]
                dest_filename = f"{timestamp_str}{file_extension}"
                dest_media = os.path.join(account_dir, 'media', dest_filename)
                
                # Debug file paths
                print(f"DEBUG: Source media path: {source_media}")
                print(f"DEBUG: Source media exists: {os.path.exists(source_media)}")
                print(f"DEBUG: Destination media path: {dest_media}")
                
                # Copy the file
                shutil.copy2(source_media, dest_media)
                print(f"DEBUG: Destination media exists after copy: {os.path.exists(dest_media)}")
                
                # Also copy to the web server's images directory for the main tool
                try:
                    web_images_dir = os.path.join(BASE_DIR, 'web', 'images', 'scheduled_post', device_id, account_name)
                    print(f"DEBUG: Creating web images directory: {web_images_dir}")
                    os.makedirs(web_images_dir, exist_ok=True)
                    web_dest_path = os.path.join(web_images_dir, dest_filename)
                    shutil.copy2(source_media, web_dest_path)
                    print(f"DEBUG: Copied media to web server path: {web_dest_path}")
                    print(f"DEBUG: Web media exists: {os.path.exists(web_dest_path)}")
                except Exception as e:
                    print(f"ERROR copying to web directory: {e}")
                    traceback.print_exc()
                
                # Store just the filename for the account-specific database
                # Based on working examples, the main tool expects just the filename
                account_media_path = dest_filename
                print(f"Media path for account database: {account_media_path}")
            
            # Connect to account's database
            account_conn = get_db_connection(account_db_path)
            account_cursor = account_conn.cursor()
            
            # Create table if it doesn't exist
            account_cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_post (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
                post_id VARCHAR, 
                file_location VARCHAR, 
                post_location VARCHAR, 
                post_music VARCHAR, 
                tag_people VARCHAR, 
                caption VARCHAR, 
                post_type VARCHAR, 
                scheduled_date VARCHAR, 
                date VARCHAR, 
                is_published INTEGER
            )
            ''')
            
            # Convert scheduled_time to format expected by main tool
            # Check if scheduled_time is already in datetime format or string format
            if isinstance(post_data['scheduled_time'], str):
                # If it's already in the format 'YYYY-MM-DD HH:MM', parse it directly
                try:
                    # Try parsing with datetime.strptime instead of fromisoformat
                    scheduled_date_obj = datetime.datetime.strptime(post_data['scheduled_time'], '%Y-%m-%d %H:%M')
                    scheduled_date = scheduled_date_obj.strftime('%Y-%m-%d %H:%M')
                except ValueError as e:
                    print(f"Error parsing scheduled_time: {e}")
                    # Fallback to current time if parsing fails
                    scheduled_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            else:
                # If it's already a datetime object
                scheduled_date = post_data['scheduled_time'].strftime('%Y-%m-%d %H:%M')
            current_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Insert into account's scheduled_post table
            account_cursor.execute('''
            INSERT INTO scheduled_post 
            (post_id, file_location, post_location, post_music, tag_people, caption, post_type, scheduled_date, date, is_published) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_id,
                account_media_path,
                post_data.get('location', ''),
                '',  # post_music
                '',  # tag_people
                post_data.get('caption', ''),
                post_data['post_type'],
                scheduled_date,
                current_date,
                0  # is_published (0 = not published)
            ))
            
            account_conn.commit()
            account_conn.close()
            
            print(f"Scheduled post {post_id} created in both central and account-specific databases")
        else:
            print(f"Warning: Account directory {account_dir} not found. Post only created in central database.")
        
        return post_id
    except Exception as e:
        print(f"Error creating scheduled post: {e}")
        traceback.print_exc()
        return None

# Function to delete a scheduled post
def delete_scheduled_post(post_id):
    try:
        # Get the post info first (we need device_id and account)
        db_path = init_scheduled_posts_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT deviceid, account, media_path FROM scheduled_posts WHERE id = ?', (post_id,))
        post = cursor.fetchone()
        
        if not post:
            return False, 'Scheduled post not found'
        
        device_id = post[0]
        account_name = post[1]
        media_path = post[2]
        
        # Delete from central database
        cursor.execute('DELETE FROM scheduled_posts WHERE id = ?', (post_id,))
        conn.commit()
        
        # Also delete from account-specific database
        account_dir = os.path.join(BASE_DIR, device_id, account_name)
        if os.path.exists(account_dir):
            account_db_path = os.path.join(account_dir, 'scheduled_post.db')
            
            if os.path.exists(account_db_path):
                account_conn = get_db_connection(account_db_path)
                account_cursor = account_conn.cursor()
                account_cursor.execute('DELETE FROM scheduled_post WHERE post_id = ?', (post_id,))
                account_conn.commit()
                account_conn.close()
                print(f"Deleted post {post_id} from account-specific database")
        
        # Delete media file if it exists
        if media_path:
            try:
                media_file_path = os.path.join(SCHEDULED_POSTS_DIR, media_path)
                if os.path.exists(media_file_path):
                    os.remove(media_file_path)
                    print(f"Deleted media file {media_file_path}")
            except Exception as e:
                print(f"Error deleting media file: {e}")
        
        conn.close()
        
        return True, 'Scheduled post deleted successfully'
    except Exception as e:
        print(f"Error deleting scheduled post {post_id}: {e}")
        traceback.print_exc()
        return False, str(e)

# Initialize caption templates database
def init_caption_templates_db():
    db_path = os.path.join(BASE_DIR, 'caption_templates.db')
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS caption_templates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS captions (
        id TEXT PRIMARY KEY,
        template_id TEXT NOT NULL,
        caption TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY (template_id) REFERENCES caption_templates(id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    return db_path

# Get all caption templates
def get_all_caption_templates():
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM caption_templates ORDER BY name')
        templates = [row_to_dict(row) for row in cursor.fetchall()]
        
        # Get caption count for each template
        for template in templates:
            cursor.execute('SELECT COUNT(*) FROM captions WHERE template_id = ?', (template['id'],))
            template['caption_count'] = cursor.fetchone()[0]
        
        conn.close()
        return templates
    except Exception as e:
        print(f"Error getting caption templates: {e}")
        return []

# Get a specific caption template with its captions
def get_caption_template(template_id):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM caption_templates WHERE id = ?', (template_id,))
        template_row = cursor.fetchone()
        
        if not template_row:
            conn.close()
            return None
            
        template = row_to_dict(template_row)
        
        cursor.execute('SELECT * FROM captions WHERE template_id = ?', (template_id,))
        template['captions'] = [row_to_dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return template
    except Exception as e:
        print(f"Error getting caption template {template_id}: {e}")
        return None

# Create a new caption template
def create_caption_template(name, description, captions):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        template_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        
        # Insert template
        cursor.execute('''
        INSERT INTO caption_templates (id, name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ''', (template_id, name, description, now, now))
        
        # Insert captions
        for caption in captions:
            caption_id = str(uuid.uuid4())
            cursor.execute('''
            INSERT INTO captions (id, template_id, caption, created_at)
            VALUES (?, ?, ?, ?)
            ''', (caption_id, template_id, caption, now))
        
        conn.commit()
        conn.close()
        
        return template_id
    except Exception as e:
        print(f"Error creating caption template: {e}")
        return None

# Update a caption template
def update_caption_template(template_id, name, description, captions):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        now = datetime.datetime.now().isoformat()
        
        # Update template
        cursor.execute('''
        UPDATE caption_templates
        SET name = ?, description = ?, updated_at = ?
        WHERE id = ?
        ''', (name, description, now, template_id))
        
        # Delete existing captions
        cursor.execute('DELETE FROM captions WHERE template_id = ?', (template_id,))
        
        # Insert new captions
        for caption in captions:
            caption_id = str(uuid.uuid4())
            cursor.execute('''
            INSERT INTO captions (id, template_id, caption, created_at)
            VALUES (?, ?, ?, ?)
            ''', (caption_id, template_id, caption, now))
        
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error updating caption template {template_id}: {e}")
        return False

# Delete a caption template
def delete_caption_template(template_id):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Delete captions first (due to foreign key constraint)
        cursor.execute('DELETE FROM captions WHERE template_id = ?', (template_id,))
        
        # Then delete the template
        cursor.execute('DELETE FROM caption_templates WHERE id = ?', (template_id,))
        
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Error deleting caption template {template_id}: {e}")
        return False

# Get random captions from a template
def get_random_captions(template_id, count=1):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Get random captions without special characters or emojis
        cursor.execute('SELECT caption FROM captions WHERE template_id = ? ORDER BY RANDOM() LIMIT ?', (template_id, count))
        captions = []
        
        for row in cursor.fetchall():
            try:
                # Remove emojis and special characters that might cause issues
                import re
                caption = row[0]
                # Keep only basic ASCII characters, letters, numbers, and basic punctuation
                cleaned_caption = re.sub(r'[^\x00-\x7F]+', '', caption)
                captions.append(cleaned_caption)
            except Exception as e:
                print(f"Error processing caption: {e}")
                # If there's an error, add a simple caption as fallback
                captions.append("Great photo!")
        
        conn.close()
        
        # If no captions were found or all were filtered out, return a default caption
        if not captions:
            return ["Great photo!"]
            
        return captions
    except Exception as e:
        print(f"Error getting random captions from template {template_id}: {e}")
        return ["Great photo!"]

# Debug function for caption templates
def debug_caption_template(template_id):
    """Debug function to check if a caption template exists and retrieve its captions"""
    try:
        print(f"\nDEBUG: Checking caption template ID: {template_id}")
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if template exists
        cursor.execute('SELECT * FROM caption_templates WHERE id = ?', (template_id,))
        template = cursor.fetchone()
        
        if template:
            print(f"DEBUG: Template found: {dict(template)}")
            
            # Get captions
            cursor.execute('SELECT * FROM captions WHERE template_id = ?', (template_id,))
            captions = cursor.fetchall()
            
            print(f"DEBUG: Found {len(captions)} captions:")
            for caption in captions:
                print(f"  - {dict(caption)['caption']}")
                
            # Test random selection
            cursor.execute('SELECT caption FROM captions WHERE template_id = ? ORDER BY RANDOM() LIMIT 1', (template_id,))
            random_caption = cursor.fetchone()
            
            if random_caption:
                print(f"DEBUG: Random caption: {random_caption[0]}")
            else:
                print("DEBUG: No random caption found")
        else:
            print(f"DEBUG: Template not found with ID: {template_id}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        traceback.print_exc()
        return False

# =============================================================================
# BASIC AUTH SYSTEM
# =============================================================================

AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auth_config.json')


def _load_auth_config():
    """Load auth config from JSON file, creating defaults if missing."""
    if not os.path.exists(AUTH_CONFIG_PATH):
        default_config = {
            'username': 'admin',
            'password_hash': generate_password_hash('hydra2026')
        }
        with open(AUTH_CONFIG_PATH, 'w') as f:
            json.dump(default_config, f, indent=2)
        _logger.info("Created default auth_config.json (admin/hydra2026)")
        return default_config
    with open(AUTH_CONFIG_PATH, 'r') as f:
        return json.load(f)


def _save_auth_config(config):
    """Save auth config to JSON file."""
    with open(AUTH_CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def _check_auth(username, password):
    """Verify username/password against stored config."""
    config = _load_auth_config()
    return (username == config.get('username')
            and check_password_hash(config.get('password_hash', ''), password))


def _auth_required_response():
    """Return a 401 response that triggers the browser Basic Auth dialog."""
    return Response(
        'Authentication required.\n', 401,
        {'WWW-Authenticate': 'Basic realm="Hydra Dashboard"'}
    )


# Ensure config exists at import time
_load_auth_config()

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024  # 512 MB per request

# ── Flask error logging ──────────────────────────────────────────────
@app.errorhandler(Exception)
def _handle_exception(e):
    """Log unhandled exceptions in route handlers to file."""
    _logger.error("Unhandled exception in request %s %s", request.method, request.path, exc_info=e)
    return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500

@app.after_request
def _log_errors(response):
    """Log 5xx responses."""
    if response.status_code >= 500:
        _logger.warning("5xx response: %s %s -> %s", request.method, request.path, response.status_code)
    return response


# ---- Basic Auth before_request hook ----
@app.before_request
def _require_basic_auth():
    """Enforce HTTP Basic Auth on all routes except /api/auth/change-password (handled separately)."""
    # Allow the change-password endpoint through (it checks auth in its own body)
    if request.path == '/api/auth/change-password' and request.method == 'POST':
        return None
    auth = request.authorization
    if not auth or not _check_auth(auth.username, auth.password):
        return _auth_required_response()
    return None


@app.route('/api/settings/ai', methods=['GET'])
def get_ai_settings():
    """Get AI configuration from global_settings.json."""
    try:
        gs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'global_settings.json')
        if os.path.exists(gs_path):
            with open(gs_path, 'r') as f:
                gs = json.load(f)
            ai = gs.get('ai', {})
            # Mask keys for display (show first 8 chars + ...)
            return jsonify({
                'openai_api_key': ai.get('openai_api_key', ''),
                'anthropic_api_key': ai.get('anthropic_api_key', ''),
                'provider': ai.get('provider', 'openai'),
                'enabled': ai.get('enabled', True),
            })
        return jsonify({'openai_api_key': '', 'anthropic_api_key': '', 'provider': 'openai', 'enabled': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/ai', methods=['POST'])
def save_ai_settings():
    """Save AI configuration to global_settings.json."""
    try:
        data = request.get_json()
        gs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'global_settings.json')

        # Load existing
        gs = {}
        if os.path.exists(gs_path):
            with open(gs_path, 'r') as f:
                gs = json.load(f)

        # Update AI section
        if 'ai' not in gs:
            gs['ai'] = {}
        if data.get('openai_api_key') is not None:
            gs['ai']['openai_api_key'] = data['openai_api_key']
        if data.get('anthropic_api_key') is not None:
            gs['ai']['anthropic_api_key'] = data['anthropic_api_key']
        if data.get('provider'):
            gs['ai']['provider'] = data['provider']
        gs['ai']['enabled'] = True

        with open(gs_path, 'w') as f:
            json.dump(gs, f, indent=4)

        return jsonify({'status': 'success', 'message': 'AI settings saved'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/change-password', methods=['POST'])
def change_password():
    """Change the dashboard password. Requires current credentials."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')

        if not current_password or not new_password:
            return jsonify({'error': 'current_password and new_password are required'}), 400

        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400

        config = _load_auth_config()
        if not check_password_hash(config.get('password_hash', ''), current_password):
            return jsonify({'error': 'Current password is incorrect'}), 403

        config['password_hash'] = generate_password_hash(new_password)
        _save_auth_config(config)
        _logger.info("Dashboard password changed successfully")

        return jsonify({'message': 'Password changed successfully'})
    except Exception as e:
        _logger.error("Error changing password: %s", e)
        return jsonify({'error': str(e)}), 500


@app.route('/settings')
def settings_page():
    """Settings page for changing dashboard password."""
    return render_template('settings_auth.html')


# Media folder watcher is in a separate script

# Register blueprints
app.register_blueprint(sources_bp)
app.register_blueprint(profile_automation_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(login_bp)
app.register_blueprint(bot_manager_bp)
app.register_blueprint(bot_settings_bp)
app.register_blueprint(bulk_import_bp)
app.register_blueprint(job_orders_bp, url_prefix='/job-orders')
app.register_blueprint(follow_list_bp)
app.register_blueprint(bot_launcher_bp)
app.register_blueprint(device_management_bp)
app.register_blueprint(import_v2_bp)
app.register_blueprint(login_v2_bp)
app.register_blueprint(job_orders_v2_bp)
app.register_blueprint(content_schedule_bp)
app.register_blueprint(farm_stats_bp)
app.register_blueprint(account_health_bp)
app.register_blueprint(proxy_bp)
app.register_blueprint(device_manager_bp)
app.register_blueprint(deploy_bp)
app.register_blueprint(comment_bp)

# ── Documentation routes ─────────────────────────────────────────────
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')

@app.route('/docs')
@app.route('/docs/')
def docs_index():
    return send_from_directory(DOCS_DIR, 'index.html')

@app.route('/docs-dev')
@app.route('/docs-dev/')
def docs_dev_index():
    return send_from_directory(DOCS_DIR, 'dev.html')

@app.route('/docs-sk')
@app.route('/docs-sk/')
def docs_sk_index():
    resp = send_from_directory(DOCS_DIR, 'sk.html')
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

@app.route('/docs/<path:filename>')
def docs_static(filename):
    return send_from_directory(DOCS_DIR, filename)

# Move this function earlier in the file to ensure it's registered properly
@app.route('/api/inventory/accounts/export', methods=['POST'])
def api_export_inventory_accounts():
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])
        
        print(f"Received account_ids: {account_ids}")  # Debug log
        
        if not account_ids:
            return jsonify({'error': 'No account IDs provided'}), 400
        
        # Get the accounts from the inventory
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Get all accounts and filter them
        cursor.execute('SELECT * FROM account_inventory')
        all_accounts = cursor.fetchall()
        
        # Convert to dictionaries and filter by ID
        accounts = []
        for row in all_accounts:
            account = row_to_dict(row)
            if str(account['id']) in account_ids:
                accounts.append(account)
        
        conn.close()
        
        print(f"Found {len(accounts)} accounts out of {len(all_accounts)} total")  # Debug log
        
        if not accounts:
            return jsonify({'error': 'No accounts found with the provided IDs'}), 404
        
        # Create CSV content
        csv_content = 'deviceid,username,password,appid,start_hour,end_hour\n'
        
        for account in accounts:
            # Default values
            device_id = account['device_assigned'] if account['device_assigned'] else ''
            username = account['username']
            password = account['password']
            app_id = 'com.instagram.android'  # Default app ID for Instagram
            start_hour = '0'  # Default start hour
            end_hour = '24'  # Default end hour
            
            # Add row to CSV
            csv_content += f'{device_id},{username},{password},{app_id},{start_hour},{end_hour}\n'
        
        # Create response with CSV file
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"accounts_export_{date_str}.csv"
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
    except Exception as e:
        print(f"Error exporting accounts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/export_csv', methods=['POST'])
def api_export_inventory_accounts_csv():
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])
        
        print(f"Received account_ids for export: {account_ids}")  # Debug log
        
        if not account_ids:
            return jsonify({'error': 'No account IDs provided'}), 400
        
        # Get the accounts from the inventory
        db_path = init_account_inventory_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Get all accounts and filter them
        cursor.execute('SELECT * FROM account_inventory')
        all_accounts = cursor.fetchall()
        
        # Convert to dictionaries and filter by ID
        accounts = []
        for row in all_accounts:
            account = row_to_dict(row)
            if str(account['id']) in account_ids:
                accounts.append(account)
        
        conn.close()
        
        print(f"Found {len(accounts)} accounts out of {len(all_accounts)} total")  # Debug log
        
        if not accounts:
            return jsonify({'error': 'No accounts found with the provided IDs'}), 404
        
        # Create CSV content
        csv_content = 'deviceid,username,password,appid,start_hour,end_hour\n'
        
        for account in accounts:
            # Default values
            device_id = account['device_assigned'] if account['device_assigned'] else ''
            username = account['username']
            password = account['password']
            app_id = 'com.instagram.android'  # Default app ID for Instagram
            start_hour = '0'  # Default start hour
            end_hour = '24'  # Default end hour
            
            # Add row to CSV
            csv_content += f'{device_id},{username},{password},{app_id},{start_hour},{end_hour}\n'
        
        # Create response with CSV file
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"accounts_export_{date_str}.csv"
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
    except Exception as e:
        print(f"Error exporting accounts: {e}")
        return jsonify({'error': str(e)}), 500

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/accounts')
def accounts():
    return render_template('accounts.html')

@app.route('/scheduled-posts')
def scheduled_posts():
    return render_template('scheduled_posts.html')

@app.route('/media-library')
def media_library():
    return render_template('media_library.html')

@app.route('/account-inventory')
def account_inventory():
    return render_template('account_inventory.html')

@app.route('/profile-automation')
def profile_automation():
    return render_template('profile_automation.html')

@app.route('/login-automation')
def login_automation():
    return render_template('login_automation.html')

@app.route('/bot-manager')
def bot_manager():
    return render_template('bot_manager.html')

@app.route('/bot-settings')
def bot_settings():
    return render_template('bot_settings.html')

@app.route('/import-accounts')
def import_accounts():
    return render_template('import_accounts.html')

@app.route('/edit-account/<account_id>')
def edit_account(account_id):
    account = get_inventory_account(account_id)
    if not account:
        return redirect('/account-inventory')
    return render_template('edit_account.html', account=account)

@app.route('/assign-account/<account_id>')
def assign_account(account_id):
    account = get_inventory_account(account_id)
    if not account:
        return redirect('/account-inventory')
    devices = get_devices()
    return render_template('assign_account.html', account=account, devices=devices)

@app.route('/test-inventory')
def test_inventory():
    return render_template('test_inventory.html')

@app.route('/debug/media')
def debug_media():
    """Debug page for media library"""
    return render_template('debug_media.html')

@app.route('/simple-media-library')
def simple_media_library():
    """Simple Media Library page that works on Windows"""
    return render_template('simple_media_library.html')

@app.route('/fixed-media-library')
def fixed_media_library():
    """Fixed Media Library page that works on Windows"""
    return render_template('fixed_media_library.html')

@app.route('/basic-media-library')
def basic_media_library():
    """Basic Media Library page that works on Windows"""
    return render_template('basic_media_library.html')

@app.route('/caption-templates')
def caption_templates_page():
    # Caption Templates page
    return render_template('caption_templates.html')

@app.route('/manage_sources')
def manage_sources_page():
    # Manage Sources page
    return render_template('manage_sources_new.html')

@app.route('/bulk_operations')
def bulk_operations_page():
    # Bulk Operations page - tag accounts by device, copy settings
    return render_template('bulk_operations.html')

# API routes
@app.route('/api/devices')
def api_devices():
    devices = get_devices()
    return jsonify(devices)

@app.route('/api/accounts')
def api_accounts():
    accounts = get_all_accounts()

    # Filter by device if provided
    device_filter = request.args.get('device')
    if device_filter:
        accounts = [a for a in accounts if a.get('deviceid') == device_filter]

    return jsonify(accounts)

@app.route('/api/account/<deviceid>/<account>')
def api_account(deviceid, account):
    accounts = get_all_accounts()
    account_data = next((a for a in accounts if a['deviceid'] == deviceid and a['account'] == account), None)
    
    if account_data:
        return jsonify(account_data)
    else:
        return jsonify({"error": "Account not found"}), 404

@app.route('/api/account/update/<deviceid>/<account>', methods=['POST'])
def api_update_account(deviceid, account):
    try:
        data = request.json
        success, message = update_account_settings(deviceid, account, data)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/dashboard/stats')
def api_dashboard_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)

@app.route('/api/scheduled_posts')
def api_scheduled_posts():
    posts = get_scheduled_posts()
    return jsonify(posts)

@app.route('/api/scheduled_posts/<post_id>', methods=['GET', 'DELETE'])
def api_scheduled_post(post_id):
    if request.method == 'GET':
        post = get_scheduled_post(post_id)
        if post:
            return jsonify(post)
        return jsonify({'error': 'Post not found'}), 404
    elif request.method == 'DELETE':
        success, message = delete_scheduled_post(post_id)
        if success:
            return jsonify({'success': True, 'message': message})
        return jsonify({'error': message}), 400

@app.route('/api/scheduled_posts', methods=['POST'])
def api_create_scheduled_post():
    try:
        # Handle multiple accounts
        accounts_json = request.form.get('accounts')
        if not accounts_json:
            return jsonify({'error': 'No accounts provided'}), 400
            
        accounts = json.loads(accounts_json)
        if not accounts:
            return jsonify({'error': 'No accounts provided'}), 400
        
        # Get other form data
        post_type = request.form.get('post_type')
        caption = request.form.get('caption', '')
        location = request.form.get('location', '')
        scheduled_time = request.form.get('scheduled_time')
        
        if not post_type or not scheduled_time:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Handle media file
        media = request.files.get('media')
        
        # Create a post for each account
        post_ids = []
        for account_data in accounts:
            post_data = {
                'deviceid': account_data['deviceid'],
                'account': account_data['account'] if isinstance(account_data['account'], str) else account_data['account']['account'],
                'post_type': post_type,
                'caption': caption,
                'location': location,
                'scheduled_time': scheduled_time
            }
            
            if media:
                post_data['media'] = media
            
            post_id = create_scheduled_post(post_data)
            if post_id:
                post_ids.append(post_id)
        
        return jsonify({
            'success': True,
            'message': f'Created {len(post_ids)} scheduled posts',
            'post_ids': post_ids
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduled_posts/<post_id>', methods=['PUT'])
def api_update_scheduled_post(post_id):
    try:
        # Get account data
        accounts_json = request.form.get('accounts')
        if not accounts_json:
            return jsonify({'error': 'No accounts provided'}), 400
            
        accounts = json.loads(accounts_json)
        if not accounts or len(accounts) == 0:
            return jsonify({'error': 'No accounts provided'}), 400
        
        # Use the first account (multi-account editing not supported for updates)
        account_data = accounts[0]
        
        # Get other form data
        post_type = request.form.get('post_type')
        caption = request.form.get('caption', '')
        location = request.form.get('location', '')
        scheduled_time = request.form.get('scheduled_time')
        
        if not post_type or not scheduled_time:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Create post data
        post_data = {
            'deviceid': account_data['deviceid'],
            'account': account_data['account'] if isinstance(account_data['account'], str) else account_data['account']['account'],
            'post_type': post_type,
            'caption': caption,
            'location': location,
            'scheduled_time': scheduled_time
        }
        
        # Handle media file
        media = request.files.get('media')
        if media:
            post_data['media'] = media
        
        # Update post
        success, message = update_scheduled_post(post_id, post_data)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduled_posts/<path:filename>')
def scheduled_post_media(filename):
    # Check if the filename contains 'media/' prefix and strip it if needed
    if filename.startswith('media/'):
        filename = filename[6:]  # Remove 'media/' prefix
    
    print(f"DEBUG: Serving scheduled post media: {filename} from {os.path.join(SCHEDULED_POSTS_DIR, 'media')}")
    return send_from_directory(os.path.join(SCHEDULED_POSTS_DIR, 'media'), filename)

@app.route('/api/bulk_update', methods=['POST'])
def api_bulk_update():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        accounts = data.get('accounts')
        settings = data.get('settings')
        
        if not accounts or not settings:
            return jsonify({'error': 'Missing accounts or settings'}), 400
        
        results = bulk_update_account_settings(accounts, settings)
        
        return jsonify({
            'success': True,
            'message': f'Updated {len(results)} accounts',
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media')
def api_media():
    try:
        tag_filter = request.args.get('tag')
        media_type_filter = request.args.get('type')
        search_term = request.args.get('search')
        
        print(f"DEBUG: Calling get_all_media with filters - tag: {tag_filter}, type: {media_type_filter}, search: {search_term}")
        media_items = get_all_media(tag_filter, media_type_filter, search_term)
        print(f"DEBUG: Found {len(media_items)} media items")
        return jsonify(media_items)
    except Exception as e:
        print(f"ERROR in /api/media: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>')
def api_media_item(media_id):
    media_item = get_media_item(media_id)
    if media_item:
        return jsonify(media_item)
    return jsonify({'error': 'Media not found'}), 404

@app.route('/api/media', methods=['POST'])
def api_add_media():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        description = request.form.get('description', '')
        tags = request.form.get('tags', '')
        folder_id = request.form.get('folder_id', '')
        
        print(f"DEBUG: Uploading media with folder_id: {folder_id}")
        
        media_id = add_media_to_library(file, description, tags)
        
        if media_id:
            # If folder_id is provided, add media to that folder
            if folder_id:
                print(f"DEBUG: Adding uploaded media {media_id} to folder {folder_id}")
                add_media_to_folder(media_id, folder_id)
            
            # Get media details to return
            media_item = get_media_item(media_id)
            if media_item:
                return jsonify(media_item)
            else:
                return jsonify({
                    'success': True,
                    'message': 'Media added successfully',
                    'id': media_id
                })
        else:
            return jsonify({'error': 'Failed to add media'}), 500
    except Exception as e:
        print(f"ERROR in api_add_media: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>', methods=['PUT'])
def api_update_media(media_id):
    try:
        description = request.json.get('description')
        tags = request.json.get('tags')
        
        success, message = update_media_item(media_id, description, tags)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>', methods=['DELETE'])
def api_delete_media(media_id):
    try:
        success, message = delete_media_item(media_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/process', methods=['POST'])
def api_process_media(media_id):
    try:
        success, message = process_image_for_antidetection(media_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/original/<path:filename>')
def media_original(filename):
    # Replace backslashes with forward slashes to fix Windows path issues
    normalized_filename = filename.replace('\\', '/')
    return send_from_directory(os.path.join(MEDIA_LIBRARY_DIR, 'original'), normalized_filename)

@app.route('/api/media/processed/<path:filename>')
def media_processed(filename):
    # Replace backslashes with forward slashes to fix Windows path issues
    normalized_filename = filename.replace('\\', '/')
    return send_from_directory(os.path.join(MEDIA_LIBRARY_DIR, 'processed'), normalized_filename)

@app.route('/api/tags')
def api_tags():
    try:
        db_path = init_media_library_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name FROM tags ORDER BY name')
        tags = [row['name'] for row in cursor.fetchall()]
        
        conn.close()
        return jsonify(tags)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts')
def api_inventory_accounts():
    try:
        accounts = get_inventory_accounts()
        return jsonify(accounts)
    except Exception as e:
        print(f"Error in API inventory accounts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts', methods=['POST'])
def api_add_inventory_accounts():
    try:
        accounts_data = request.json
        if not accounts_data:
            return jsonify({'error': 'No data provided'}), 400
        
        added_count, skipped_count = add_accounts_to_inventory(accounts_data)
        
        return jsonify({
            'success': True,
            'message': f'Added {added_count} accounts to inventory, skipped {skipped_count} duplicates'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/<account_id>')
def api_get_inventory_account(account_id):
    try:
        account = get_inventory_account(account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        return jsonify(account)
    except Exception as e:
        print(f"Error getting inventory account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/<account_id>', methods=['PUT'])
def api_update_inventory_account(account_id):
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Update the account
        success = update_inventory_account(account_id, data)
        if not success:
            return jsonify({'error': 'Failed to update account'}), 500
        
        return jsonify({'success': True, 'message': 'Account updated successfully'})
    except Exception as e:
        print(f"Error updating inventory account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/<account_id>/assign', methods=['POST'])
def api_assign_inventory_account(account_id):
    try:
        data = request.json
        if not data or 'device_id' not in data:
            return jsonify({'error': 'No device ID provided'}), 400
        
        device_id = data['device_id']
        
        # Get the account
        account = get_inventory_account(account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        # Call the function to assign account to device
        success, message = assign_account_to_device(account_id, device_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        print(f"Error assigning inventory account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/<account_id>', methods=['DELETE'])
def api_delete_inventory_account(account_id):
    try:
        success, message = delete_inventory_account(account_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/import', methods=['POST'])
def api_import_inventory_accounts():
    try:
        # Try to get JSON data
        if request.is_json:
            data = request.json
            accounts_text = data.get('accounts_text')
        # If not JSON, try form data
        else:
            accounts_text = request.form.get('accounts_text')
            if not accounts_text:
                # Try to parse raw data
                try:
                    raw_data = request.get_data().decode('utf-8')
                    import json
                    data = json.loads(raw_data)
                    accounts_text = data.get('accounts_text')
                except:
                    accounts_text = None
        
        print(f"Received import request with accounts_text: {accounts_text}")
        
        if not accounts_text:
            print("No accounts text provided")
            return jsonify({'error': 'No accounts text provided'}), 400
        
        accounts_data = parse_accounts_from_text(accounts_text)
        if not accounts_data:
            print("No valid accounts found in text")
            return jsonify({'error': 'No valid accounts found in text'}), 400
        
        result = add_accounts_to_inventory(accounts_data)
        
        if isinstance(result, tuple) and len(result) == 2:
            added_count, skipped_count = result
            print(f"Added {added_count} accounts, skipped {skipped_count}")
            
            return jsonify({
                'success': True,
                'message': f'Added {added_count} accounts to inventory, skipped {skipped_count} duplicates',
                'added': added_count,
                'skipped': skipped_count
            })
        else:
            # Handle the case where the old format is returned (True/False, message)
            success, message = result
            if success is True and isinstance(message, str):
                # Try to extract numbers from the message
                import re
                # Print the message for debugging
                print(f"Parsing message: {message}")
                
                # More flexible regex patterns to handle different message formats
                added_match = re.search(r'Added\s+(\d+)', message)
                skipped_match = re.search(r'skipped\s+(\d+)', message)
                
                added = int(added_match.group(1)) if added_match else 0
                skipped = int(skipped_match.group(1)) if skipped_match else 0
                
                return jsonify({
                    'success': True,
                    'message': message,
                    'added': added,
                    'skipped': skipped
                })
            
            return jsonify({
                'success': success,
                'message': message,
                'added': 0,
                'skipped': 0
            })
    except Exception as e:
        print(f"Error importing accounts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/filter')
def api_filter_inventory_accounts():
    try:
        status = request.args.get('status')
        search = request.args.get('search')
        
        accounts = get_all_inventory_accounts(status_filter=status, search_term=search)
        return jsonify(accounts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/accounts/bulk-update', methods=['POST'])
def api_bulk_update_inventory_accounts():
    try:
        data = request.json
        print(f"Received bulk update request with data: {data}")
        
        if not data or 'account_ids' not in data or 'status' not in data:
            return jsonify({'error': 'Account IDs and status are required'}), 400
        
        account_ids = data['account_ids']
        status = data['status']
        print(f"Processing account_ids: {account_ids}, type: {type(account_ids)}")
        print(f"Status: {status}")
        
        if not account_ids or not isinstance(account_ids, list):
            return jsonify({'error': 'Account IDs must be a non-empty list'}), 400
        
        if status not in ['available', 'used']:
            return jsonify({'error': 'Status must be either "available" or "used"'}), 400
        
        # Get the accounts that are currently visible in the UI
        # This ensures we're using the same database connection as the rest of the application
        existing_accounts = get_inventory_accounts()
        print(f"Existing accounts from get_inventory_accounts(): {len(existing_accounts)}")
        if existing_accounts:
            print(f"First few accounts: {existing_accounts[:3]}")
        
        # Filter the accounts to update only those that exist
        account_id_set = set(account_ids)
        accounts_to_update = [acc for acc in existing_accounts if acc['id'] in account_id_set]
        print(f"Found {len(accounts_to_update)} accounts to update")
        
        if not accounts_to_update:
            return jsonify({
                'success': False,
                'message': 'None of the selected accounts were found in the database',
                'updated_count': 0
            })
        
        # Update each account individually using the same function that works for individual updates
        now = datetime.datetime.now().isoformat()
        updated_count = 0
        
        for account in accounts_to_update:
            # Prepare update data
            update_data = {
                'status': status
            }
            
            if status == 'used':
                update_data['date_used'] = now
            
            # Update the account using the existing function that works
            success = update_inventory_account(account['id'], update_data)
            
            if success:
                updated_count += 1
                print(f"Successfully updated account {account['id']} ({account.get('username', 'unknown')})")
            else:
                print(f"Failed to update account {account['id']} ({account.get('username', 'unknown')})")
        
        result = {
            'success': True,
            'message': f'Updated {updated_count} accounts to status "{status}"',
            'updated_count': updated_count
        }
        print(f"Returning result: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"Error in bulk update: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/stats')
def api_inventory_stats():
    try:
        # Get all accounts
        accounts = get_inventory_accounts()
        
        # Get current date
        now = datetime.datetime.now()
        seven_days_ago = (now - datetime.timedelta(days=7)).isoformat()
        
        # Count accounts by status
        total_accounts = len(accounts)
        available_accounts = sum(1 for account in accounts if account['status'] == 'available')
        used_accounts = sum(1 for account in accounts if account['status'] == 'used')
        
        # Count recently added and used accounts
        recently_added = sum(1 for account in accounts if account['date_added'] and account['date_added'] >= seven_days_ago)
        recently_used = sum(1 for account in accounts if account['date_used'] and account['date_used'] >= seven_days_ago)
        
        return jsonify({
            'total': total_accounts,
            'available': available_accounts,
            'used': used_accounts,
            'recently_added': recently_added,
            'recently_used': recently_used
        })
    except Exception as e:
        print(f"Error getting inventory stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/remove_account_from_device', methods=['POST'])
def handle_remove_account_from_device():
    data = request.get_json()
    device_id = data.get('device_id')
    username = data.get('username')
    
    if not device_id or not username:
        return jsonify({'success': False, 'message': 'Device ID and username are required'})
    
    success, message = remove_account_from_device(device_id, username)
    return jsonify({'success': success, 'message': message})

@app.route('/api/inventory/accounts/<int:account_id>/remove', methods=['POST'])
def handle_remove_account_api(account_id):
    data = request.get_json()
    device_id = data.get('device_id')
    
    if not device_id:
        return jsonify({'success': False, 'error': 'Device ID is required'})
    
    # Get account details
    db_path = init_account_inventory_db()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Find account by ID
    cursor.execute('SELECT * FROM account_inventory WHERE id = ?', (account_id,))
    account = cursor.fetchone()
    
    if not account:
        conn.close()
        return jsonify({'success': False, 'error': 'Account not found'})
    
    username = account['username']
    conn.close()
    
    # Remove account from device
    success, message = remove_account_from_device(device_id, username)
    
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'error': message})

@app.route('/test_export', methods=['GET'])
def test_export():
    return jsonify({'status': 'success', 'message': 'Test endpoint is working!'})

@app.route('/export_accounts', methods=['POST'])
def export_accounts():
    try:
        # Get account IDs from form data
        account_ids_json = request.form.get('account_ids', '[]')
        account_ids = json.loads(account_ids_json)
        
        # Get device ID if provided
        device_id = request.form.get('device_id', '')
        
        # Get mark_as_used parameter (default to True if not provided)
        mark_as_used = request.form.get('mark_as_used', 'true').lower() == 'true'
        
        print(f"Received account_ids for export: {account_ids}")  # Debug log
        print(f"Using device ID: {device_id if device_id else 'None provided'}")  # Debug log
        print(f"Mark as used: {mark_as_used}")  # Debug log
        
        if not account_ids:
            return "No account IDs provided", 400
        
        # Get all accounts from the inventory using the same approach as other functions
        print(f"Using database path: {ACCOUNT_INVENTORY_DB}")  # Debug log
        
        # Check if the database file exists
        if not os.path.exists(ACCOUNT_INVENTORY_DB):
            print(f"Database file does not exist at: {ACCOUNT_INVENTORY_DB}")
            return "Database file not found", 500
        
        # Connect to the database
        conn = sqlite3.connect(ACCOUNT_INVENTORY_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all accounts
        cursor.execute('SELECT * FROM account_inventory')
        all_accounts = cursor.fetchall()
        print(f"Total accounts in database: {len(all_accounts)}")  # Debug log
        
        # Convert to dictionaries and filter by ID
        accounts = []
        for row in all_accounts:
            account = dict(row)
            if str(account['id']) in account_ids:
                accounts.append(account)
                print(f"Matched account: id={account['id']}, username={account['username']}")  # Debug log
        
        # If mark_as_used is true, update the status of all exported accounts to 'used'
        if mark_as_used:
            current_time = datetime.datetime.now().isoformat()
            for account in accounts:
                # Only update if the account is currently 'available'
                if account['status'] == 'available':
                    account_data = {
                        'status': 'used',
                        'date_used': current_time
                    }
                    update_inventory_account(account['id'], account_data)
                    print(f"Marked account {account['username']} (ID: {account['id']}) as used")
        
        conn.close()
        
        print(f"Found {len(accounts)} accounts out of {len(all_accounts)} total")  # Debug log
        
        if not accounts:
            return "No accounts found with the provided IDs", 404
        
        # Create CSV content
        csv_content = 'deviceid,username,password,appid,start_hour,end_hour,2fa_setup_code\n'

        for index, account in enumerate(accounts):
            # Use provided device ID if available, otherwise use the assigned device
            account_device_id = device_id if device_id else (account['device_assigned'] if account['device_assigned'] else '')
            username = account['username']
            password = account['password']
            two_fa_token = account.get('two_factor_auth', '')  # Get 2FA token, default to empty string if not present

            # Determine appid - increment last letter for each account
            # Start from 'e' (ASCII 101) and increment for each account
            letter_code = 101 + index  # 101 = 'e', 102 = 'f', etc.
            letter = chr(letter_code)
            app_id = f'com.instagram.androi{letter}'

            # Allocate 2-hour time slots for each account
            start_hour = str(index * 2)  # 0, 2, 4, 6, ...
            end_hour = str((index * 2) + 2)  # 2, 4, 6, 8, ... (no wrapping, goes to 24)

            # Add row to CSV
            csv_content += f'{account_device_id},{username},{password},{app_id},{start_hour},{end_hour},{two_fa_token}\n'
        
        # Create response with CSV file
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"accounts_export_{date_str}.csv"
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
    except Exception as e:
        print(f"Error exporting accounts: {e}")
        return f"Error exporting accounts: {e}", 500

@app.route('/api/accounts/<deviceid>/<account>/media/<path:filename>')
def account_media(deviceid, account, filename):
    account_dir = os.path.join(BASE_DIR, deviceid, account, 'media')
    print(f"Serving media from {account_dir}, filename: {filename}")
    
    # Check if file exists
    full_path = os.path.join(account_dir, filename)
    if not os.path.exists(full_path):
        print(f"WARNING: Media file not found at {full_path}")
        # Try to find the file by basename in case the path structure is different
        basename = os.path.basename(filename)
        alt_path = os.path.join(account_dir, basename)
        if os.path.exists(alt_path):
            print(f"Found media at alternate path: {alt_path}")
            return send_from_directory(account_dir, basename)
        return jsonify({"error": "Media file not found"}), 404
    
    return send_from_directory(account_dir, filename)

@app.route('/api/jap/services', methods=['GET'])
def api_jap_services():
    """
    API endpoint to get JustAnotherPanel services
    """
    if not JAP_API_KEY:
        return jsonify({'error': 'API key not configured'}), 400
        
    services = get_jap_services()
    return jsonify(services)

@app.route('/api/jap/order-followers', methods=['POST'])
def api_order_followers():
    """
    API endpoint to order Instagram followers
    """
    try:
        data = request.form
        username = data.get('username')
        quantity = int(data.get('quantity', 0))
        service_id = int(data.get('service_id', 0) or 0)
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
            
        if quantity <= 0:
            return jsonify({'error': 'Quantity must be greater than 0'}), 400
            
        result = order_instagram_followers(username, quantity, service_id or None)
        
        if 'error' in result:
            return jsonify(result), 400
            
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jap/orders', methods=['GET'])
def api_get_orders():
    """
    API endpoint to get follower orders
    """
    try:
        username = request.args.get('username')
        orders = get_follower_orders(username)
        return jsonify(orders)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jap/order-status/<order_id>', methods=['GET'])
def api_order_status(order_id):
    """
    API endpoint to check order status
    """
    try:
        status = check_order_status(order_id)
        
        # Update the status in our database
        if 'status' in status and not 'error' in status:
            update_order_status(order_id, status['status'])
            
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jap-settings', methods=['GET', 'POST'])
def jap_settings():
    """
    Page to manage JustAnotherPanel API settings
    """
    global JAP_API_KEY
    
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        
        if api_key:
            # In a production environment, this should be stored securely, not hardcoded
            # For example, in an encrypted database or using a secure key management service
            # This is a simplified implementation for demonstration purposes
            JAP_API_KEY = api_key
            
            # Save the API key to a file for persistence
            try:
                with open(JAP_API_KEY_FILE, 'w') as f:
                    f.write(api_key)
                save_success = True
            except Exception as e:
                print(f"Error saving API key: {e}")
                save_success = False
            
            # Test the API key
            services = get_jap_services()
            if isinstance(services, list) and services:
                message = 'API key saved and verified successfully!'
                if not save_success:
                    message += ' (Note: Could not save to file, key will be lost on restart)'
                return render_template('jap_settings.html', message=message, api_key=JAP_API_KEY)
            else:
                error = 'Invalid API key or API error'
                if save_success:
                    error += ' (Key was saved but could not be verified)'
                return render_template('jap_settings.html', error=error, api_key=JAP_API_KEY)
        else:
            return render_template('jap_settings.html', error='API key is required', api_key=JAP_API_KEY)
    
    # Load the API key from file on page load (if not already loaded)
    if not JAP_API_KEY:
        try:
            if os.path.exists(JAP_API_KEY_FILE):
                with open(JAP_API_KEY_FILE, 'r') as f:
                    JAP_API_KEY = f.read().strip()
        except Exception as e:
            print(f"Error loading API key: {e}")
    
    return render_template('jap_settings.html', api_key=JAP_API_KEY)

# Folder management API endpoints
@app.route('/api/folders', methods=['GET'])
def api_folders():
    """API endpoint to get all folders"""
    try:
        folders = get_all_folders()
        return jsonify(folders)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders/<folder_id>', methods=['GET'])
def api_folder(folder_id):
    """API endpoint to get a specific folder"""
    try:
        folder = get_folder(folder_id)
        if folder:
            return jsonify(folder)
        else:
            return jsonify({'error': 'Folder not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders', methods=['POST'])
def api_create_folder():
    """API endpoint to create a new folder"""
    try:
        data = request.json
        folder_name = data.get('name')
        description = data.get('description', '')
        parent_id = data.get('parent_id')
        
        if not folder_name:
            return jsonify({'error': 'Folder name is required'}), 400
        
        folder_id = create_media_folder(folder_name, description, parent_id)
        if folder_id:
            return jsonify({'id': folder_id, 'name': folder_name}), 201
        else:
            return jsonify({'error': 'Failed to create folder'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders/<folder_id>', methods=['PUT'])
def api_update_folder(folder_id):
    """API endpoint to update a folder"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')
        parent_id = data.get('parent_id')
        
        success = update_folder(folder_id, name, description, parent_id)
        if success:
            return jsonify({'message': 'Folder updated successfully'})
        else:
            return jsonify({'error': 'Failed to update folder'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders/<folder_id>', methods=['DELETE'])
def api_delete_folder(folder_id):
    """API endpoint to delete a folder"""
    try:
        success, message = delete_folder(folder_id)
        if success:
            return jsonify({'message': message})
        else:
            return jsonify({'error': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders/<folder_id>/media', methods=['GET'])
def api_folder_media(folder_id):
    """API endpoint to get media in a folder"""
    try:
        print(f"DEBUG: Fetching media for folder_id: {folder_id}")
        tag_filter = request.args.get('tag')
        media_type_filter = request.args.get('type')
        search_term = request.args.get('search')
        
        media_items = get_media_in_folder(folder_id, tag_filter, media_type_filter, search_term)
        print(f"DEBUG: Found {len(media_items)} media items in folder {folder_id}")
        return jsonify(media_items)
    except Exception as e:
        print(f"ERROR in api_folder_media: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/folders', methods=['POST'])
def api_add_media_to_folder(media_id):
    """API endpoint to add media to a folder"""
    try:
        print(f"DEBUG: Adding media {media_id} to folder")
        data = request.json
        folder_id = data.get('folder_id')
        
        if not folder_id:
            return jsonify({'error': 'Folder ID is required'}), 400
        
        success = add_media_to_folder(media_id, folder_id)
        if success:
            return jsonify({'message': 'Media added to folder successfully'})
        else:
            return jsonify({'error': 'Failed to add media to folder'}), 500
    except Exception as e:
        print(f"ERROR adding media {media_id} to folder: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<media_id>/folders/<folder_id>', methods=['DELETE'])
def api_remove_media_from_folder(media_id, folder_id):
    """API endpoint to remove media from a folder"""
    try:
        success = remove_media_from_folder(media_id, folder_id)
        if success:
            return jsonify({'message': 'Media removed from folder successfully'})
        else:
            return jsonify({'error': 'Failed to remove media from folder'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Function to get account runtime hours
def get_account_runtime_hours(device_id, account_name):
    """
    Get the runtime hours for a specific account
    Returns a list of tuples with (start_hour, end_hour) in 24-hour format
    """
    try:
        print(f"Getting runtime hours for {account_name} on device {device_id}")
        
        # Check if the account has runtime hours in the accounts.db
        # This is where the runtime hours are actually stored in your system
        accounts_db_path = os.path.join(BASE_DIR, device_id, 'accounts.db')
        print(f"Looking for runtime hours in: {accounts_db_path}")
        
        if os.path.exists(accounts_db_path):
            conn = get_db_connection(accounts_db_path)
            cursor = conn.cursor()
            
            # First, check if the account exists in the database
            cursor.execute("SELECT account FROM accounts WHERE account = ?", (account_name,))
            account_exists = cursor.fetchone()
            
            if not account_exists:
                print(f"WARNING: Account '{account_name}' not found in accounts.db!")
            
            # Get runtime hours from the accounts table
            # The columns are named 'starttime' and 'endtime' based on dashboard.js
            cursor.execute("SELECT starttime, endtime FROM accounts WHERE account = ?", (account_name,))
            account_data = cursor.fetchone()
            
            if account_data:
                print(f"Raw runtime data from accounts.db: starttime={account_data[0]}, endtime={account_data[1]}")
            
            if account_data and account_data[0] is not None and account_data[1] is not None:
                try:
                    # Handle different formats of time storage
                    # First, try to extract hour from formats like '16:00'
                    runtime_start = account_data[0]
                    runtime_end = account_data[1]
                    
                    # If the format is like '16:00', extract just the hour
                    if isinstance(runtime_start, str) and ':' in runtime_start:
                        runtime_start = int(runtime_start.split(':')[0])
                    else:
                        runtime_start = int(runtime_start)
                        
                    if isinstance(runtime_end, str) and ':' in runtime_end:
                        runtime_end = int(runtime_end.split(':')[0])
                    else:
                        runtime_end = int(runtime_end)
                    
                    # Only use if they're valid hours (0-23)
                    if 0 <= runtime_start <= 23 and 0 <= runtime_end <= 23 and runtime_start != runtime_end:
                        print(f"SUCCESS: Found valid runtime hours for {account_name}: {runtime_start}-{runtime_end}")
                        conn.close()
                        return [(runtime_start, runtime_end)]
                    else:
                        print(f"WARNING: Invalid runtime hours found: start={runtime_start}, end={runtime_end}")
                        # Special case: If end_hour is 24, treat it as valid and convert to 0
                        if runtime_end == 24:
                            runtime_end = 0
                            print(f"Converted end hour 24 to 0: {runtime_start}-{runtime_end}")
                            conn.close()
                            return [(runtime_start, runtime_end)]
                except (ValueError, TypeError) as e:
                    print(f"Error converting runtime hours: {e}")
            else:
                print(f"No runtime hours found in accounts.db for {account_name}")
            
            conn.close()
        else:
            print(f"WARNING: accounts.db not found at {accounts_db_path}")
        
        # If we couldn't find runtime hours in accounts.db, check account.db
        account_dir = os.path.join(BASE_DIR, device_id, account_name)
        db_path = os.path.join(account_dir, 'account.db')
        print(f"Looking for account-specific runtime hours in: {db_path}")
        
        if not os.path.exists(db_path):
            print(f"Account database not found for {account_name}, using default runtime hours")
            return [(0, 2), (10, 12), (14, 16)]  # Default runtime hours
        
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if the runtime_hours table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runtime_hours'")
        if not cursor.fetchone():
            print(f"runtime_hours table not found in account.db, creating with default values")
            # Create the runtime_hours table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS runtime_hours (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_hour INTEGER NOT NULL,
                end_hour INTEGER NOT NULL
            )
            ''')
            # Insert default runtime hours
            cursor.execute("INSERT INTO runtime_hours (start_hour, end_hour) VALUES (0, 2)")
            cursor.execute("INSERT INTO runtime_hours (start_hour, end_hour) VALUES (10, 12)")
            cursor.execute("INSERT INTO runtime_hours (start_hour, end_hour) VALUES (14, 16)")
            conn.commit()
            print(f"Created default runtime hours for {account_name}")
        
        # Get runtime hours from the database
        cursor.execute("SELECT start_hour, end_hour FROM runtime_hours")
        runtime_hours = cursor.fetchall()
        
        conn.close()
        
        if not runtime_hours:
            print(f"No runtime hours found in account.db, using default values")
            return [(0, 2), (10, 12), (14, 16)]  # Default runtime hours if none found
        
        print(f"SUCCESS: Found runtime hours in account.db for {account_name}: {runtime_hours}")
        return runtime_hours
    except Exception as e:
        print(f"ERROR: Exception getting runtime hours for {account_name}: {e}")
        traceback.print_exc()
        print(f"Using default runtime hours due to error")
        return [(0, 2), (10, 12), (14, 16)]  # Default runtime hours on error

# Function to adjust scheduled time to fit within runtime hours
def adjust_time_to_runtime_hours(scheduled_time, runtime_hours):
    """
    Adjust the scheduled time to fit within the account's runtime hours
    If the time is already within runtime hours, it's returned unchanged
    Otherwise, it's moved to the next available runtime slot
    """
    # If no runtime hours defined, return the original time
    if not runtime_hours:
        print(f"No runtime hours defined, using original time: {scheduled_time}")
        return scheduled_time
    
    print(f"Adjusting time {scheduled_time} to fit runtime hours: {runtime_hours}")
    
    # Get the hour of the scheduled time
    hour = scheduled_time.hour
    
    # Check if the hour is already within any runtime slot
    for start_hour, end_hour in runtime_hours:
        if start_hour <= hour < end_hour:
            # Time is already within runtime hours
            print(f"Time {scheduled_time} is already within runtime hours slot ({start_hour}-{end_hour})")
            return scheduled_time
    
    # If we're here, the time is outside runtime hours
    # Find the next available runtime slot
    print(f"Time {scheduled_time} is outside runtime hours, finding next available slot")
    
    # Sort runtime hours by start time
    sorted_runtime = sorted(runtime_hours)
    
    # Try to find a slot later today
    for start_hour, end_hour in sorted_runtime:
        if hour < start_hour:
            # Found a slot later today
            # Set time to the start of this slot plus a fixed offset (20 minutes)
            # Using a fixed offset instead of random for more predictable scheduling
            offset_minutes = 20
            new_time = scheduled_time.replace(
                hour=start_hour,
                minute=offset_minutes
            )
            print(f"Adjusted to next available slot today: {new_time} (slot: {start_hour}-{end_hour})")
            return new_time
    
    # If no slot found later today, use the first slot tomorrow
    start_hour, end_hour = sorted_runtime[0]
    offset_minutes = 20
    new_time = scheduled_time + datetime.timedelta(days=1)
    new_time = new_time.replace(
        hour=start_hour,
        minute=offset_minutes
    )
    print(f"No slots available today, adjusted to tomorrow's first slot: {new_time} (slot: {start_hour}-{end_hour})")
    return new_time

# Function to schedule within runtime hours
def schedule_within_runtime_hours(device_id, account_name, scheduled_time):
    """
    Ensure a post is scheduled within an account's runtime hours
    """
    # Get runtime hours for this account
    runtime_hours = get_account_runtime_hours(device_id, account_name)
    
    # Adjust the scheduled time to fit within runtime hours
    adjusted_time = adjust_time_to_runtime_hours(scheduled_time, runtime_hours)
    
    return adjusted_time

@app.route('/api/batch/schedule', methods=['POST'])
def api_batch_schedule():
    """API endpoint to schedule posts for all media in a folder"""
    try:
        data = request.json
        folder_id = data.get('folder_id')
        device_id = data.get('device_id')
        account = data.get('account')
        use_all_accounts = data.get('use_all_accounts', False)
        caption_template_id = data.get('caption_template_id', '')
        caption_template = data.get('caption_template', '')
        hashtags = data.get('hashtags', '')
        start_time = data.get('start_time')
        interval_hours = int(data.get('interval_hours', 24))
        repurpose = data.get('repurpose', False)
        
        if not all([folder_id, device_id, start_time]) or (not use_all_accounts and not account):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Get all accounts for the device if use_all_accounts is True
        accounts = []
        if use_all_accounts:
            try:
                # Get accounts for the device using the get_accounts function
                # This uses the device-specific accounts.db instead of the main devices.db
                device_accounts = get_accounts(device_id)
                
                if device_accounts:
                    accounts = [{'account': account['account']} for account in device_accounts]
                else:
                    return jsonify({'error': 'No accounts found for this device'}), 404
            except Exception as e:
                return jsonify({'error': f'Error fetching accounts: {str(e)}'}), 500
        else:
            accounts = [{'account': account}]
            
        # Get the requested post type (default to regular post/reels if not specified)
        requested_post_type = data.get('post_type', None)
        
        # Get all media in the folder
        media_items = get_media_in_folder(folder_id)
        if not media_items:
            return jsonify({'error': 'No media found in folder'}), 404
        
        # Schedule posts for each account with randomized media order
        scheduled_posts = []
        initial_start_time = datetime.datetime.fromisoformat(start_time)

        for account_data in accounts:
            account_name = account_data['account'] if isinstance(account_data, dict) and 'account' in account_data else account_data
            # current_time_for_account = initial_start_time # This will be set per post
            
            # Create a shuffled list of media items for this account
            media_items_shuffled = list(media_items) # Create a copy
            random.shuffle(media_items_shuffled)
            
            for i, media in enumerate(media_items_shuffled):
                media_id = media['id']
                media_item_details = get_media_item(media_id)
                
                if not media_item_details:
                    print(f"Skipping media_id {media_id} for account {account_name} as details not found.")
                    continue
                
                # Calculate the base scheduled time for this specific post for this account
                # Each post for an account is offset by the interval from the account's initial start time
                base_schedule_time_for_post = initial_start_time + datetime.timedelta(hours=interval_hours * i)
                adjusted_schedule_time = schedule_within_runtime_hours(device_id, account_name, base_schedule_time_for_post)
                # print(f"Scheduled time for {account_name}, media {media_item_details['filename']}: {adjusted_schedule_time.strftime('%Y-%m-%d %H:%M')}")

                # Generate caption with template (caption is per-post, so regenerate/fetch here)
                item_caption = caption_template # Start with the base template
                if caption_template_id:
                    try:
                        # print(f"Getting random caption from template ID: {caption_template_id} for account {account_name}")
                        random_captions = get_random_captions(caption_template_id, 1)
                        if random_captions:
                            item_caption = random_captions[0]
                            # print(f"Using random caption for account {account_name}: {item_caption}")
                    except Exception as e:
                        print(f"Error getting random caption from template {caption_template_id} for account {account_name}: {e}")
                
                # Replace placeholders in caption using the specific post's schedule time
                temp_item_caption = item_caption # Work with a copy for replacements
                if temp_item_caption and '{filename}' in temp_item_caption:
                    temp_item_caption = temp_item_caption.replace('{filename}', os.path.splitext(media_item_details['filename'])[0])
                if temp_item_caption and '{date}' in temp_item_caption:
                    temp_item_caption = temp_item_caption.replace('{date}', adjusted_schedule_time.strftime('%Y-%m-%d'))
                if temp_item_caption and '{time}' in temp_item_caption:
                    temp_item_caption = temp_item_caption.replace('{time}', adjusted_schedule_time.strftime('%H:%M'))
                
                if hashtags:
                    temp_item_caption += f"\n\n{hashtags}"
                
                formatted_time = adjusted_schedule_time.strftime('%Y-%m-%d %H:%M')
                
                if requested_post_type:
                    post_type = requested_post_type
                else:
                    post_type = 'post' if media['media_type'] == 'image' else 'reels'
                
                post_data = {
                    'deviceid': device_id,
                    'account': account_name,
                    'post_type': post_type,
                    'caption': temp_item_caption,
                    'scheduled_time': formatted_time
                }
                
                if 'original_path' in media_item_details and media_item_details['original_path']:
                    current_file_path = os.path.normpath(os.path.join(MEDIA_LIBRARY_DIR, media_item_details['original_path']))
                    
                    if not os.path.exists(current_file_path):
                        # print(f"Warning: Original file {current_file_path} not found for account {account_name}, media {media_item_details['filename']}")
                        file_base, file_ext = os.path.splitext(media_item_details['filename'])
                        hash_filename = f"{media_item_details['id']}{file_ext}"
                        hash_path = os.path.normpath(os.path.join(MEDIA_LIBRARY_DIR, 'original', hash_filename))
                        
                        if os.path.exists(hash_path):
                            current_file_path = hash_path
                            print(f"Found file using hash-based name: {current_file_path}")
                        else:
                            print(f"No valid file path found for {media_item_details['filename']} for account {account_name}, skipping this media item.")
                            continue
                    
                    from io import BytesIO
                    try:
                        with open(current_file_path, 'rb') as f:
                            file_content = f.read()
                        file_obj = BytesIO(file_content)
                        file_obj.filename = os.path.basename(current_file_path)
                        
                        post_data['media'] = file_obj
                        
                        post_id = create_scheduled_post(post_data)
                        if post_id:
                            scheduled_posts.append({
                                'post_id': post_id,
                                'media_id': media['id'],
                                'account': account_name,
                                'scheduled_time': formatted_time,
                                'media_filename': media_item_details['filename']
                            })
                            print(f"Successfully scheduled post for account {account_name} with media {os.path.basename(current_file_path)}")
                        else:
                            print(f"Failed to schedule post for account {account_name} with media {os.path.basename(current_file_path)}")
                    except Exception as e_file_op:
                        print(f"Error processing file {current_file_path} for account {account_name}: {e_file_op}")
                        # traceback.print_exc()
                        continue # Skip this media item for this account if file operation fails
                else:
                    print(f"Warning: Cannot schedule post for account {account_name}, media {media_item_details['filename']} because media file path not found in details.")
            # End of media loop for one account
        # End of accounts loop
        
        return jsonify({
            'message': f'Successfully scheduled {len(scheduled_posts)} posts',
            'scheduled_posts': scheduled_posts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API endpoints for caption templates
@app.route('/api/caption-templates', methods=['GET'])
def api_get_caption_templates():
    try:
        templates = get_all_caption_templates()
        return jsonify(templates)
    except Exception as e:
        print(f"Error getting caption templates: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/caption-templates/<template_id>', methods=['GET'])
def api_get_caption_template(template_id):
    try:
        template = get_caption_template(template_id)
        if template:
            return jsonify(template)
        else:
            return jsonify({'error': 'Caption template not found'}), 404
    except Exception as e:
        print(f"Error getting caption template {template_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/caption-templates', methods=['POST'])
def api_create_caption_template():
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        captions_text = data.get('captions', '')
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        # Split captions by newline and filter out empty lines
        captions = [caption.strip() for caption in captions_text.split('\n') if caption.strip()]
        
        if not captions:
            return jsonify({'error': 'At least one caption is required'}), 400
        
        template_id = create_caption_template(name, description, captions)
        if template_id:
            return jsonify({
                'id': template_id,
                'message': 'Caption template created successfully'
            })
        return jsonify({'error': 'Failed to create caption template'}), 500
    except Exception as e:
        print(f"Error creating caption template: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/caption-templates/<template_id>', methods=['PUT'])
def api_update_caption_template(template_id):
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        captions_text = data.get('captions', '')
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        # Split captions by newline and filter out empty lines
        captions = [caption.strip() for caption in captions_text.split('\n') if caption.strip()]
        
        if not captions:
            return jsonify({'error': 'At least one caption is required'}), 400
        
        success = update_caption_template(template_id, name, description, captions)
        if success:
            return jsonify({'message': 'Caption template updated successfully'})
        return jsonify({'error': 'Failed to update caption template'}), 500
    except Exception as e:
        print(f"Error updating caption template {template_id}: {e}")
        return jsonify({'error': str(e)}), 500

def api_delete_caption_template(template_id):
    try:
        success = delete_caption_template(template_id)
        if success:
            return jsonify({'message': 'Caption template deleted successfully'})
        return jsonify({'error': 'Failed to delete caption template'}), 500
    except Exception as e:
        print(f"Error deleting caption template {template_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/caption-templates/<template_id>/random', methods=['GET'])
def api_get_random_caption(template_id):
    try:
        count = request.args.get('count', 1, type=int)
        captions = get_random_captions(template_id, count)
        if captions:
            return jsonify(captions)
        return jsonify({'error': 'No captions found for this template'}), 404
    except Exception as e:
        print(f"Error getting random caption from template {template_id}: {e}")
        return jsonify({'error': str(e)}), 500

# API endpoint for bulk account settings updates
@app.route('/api/accounts/bulk-settings', methods=['POST'])
def api_bulk_account_settings():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        accounts = data.get('accounts', [])
        settings = data.get('settings', {})
        
        if not accounts:
            return jsonify({'error': 'No accounts provided'}), 400
        
        if not settings:
            return jsonify({'error': 'No settings provided'}), 400
        
        # Log the received data for debugging
        print(f"Received bulk settings update request:")
        print(f"Settings: {settings}")
        print(f"Number of accounts: {len(accounts)}")
        
        # Validate settings
        if 'sharepost_mention' in settings and not settings['sharepost_mention'].strip():
            return jsonify({'error': 'Sharepost mention cannot be empty'}), 400
            
        # Import the update_account_settings helper
        from update_account_settings import update_account_settings_bulk
        
        # Process each account
        updated_accounts = 0
        failed_accounts = []
        
        for account in accounts:
            device_id = account.get('device_id')
            account_name = account.get('account_name')
            
            if not device_id or not account_name:
                failed_accounts.append({
                    'account_id': f"{device_id}/{account_name}",
                    'error': 'Missing device_id or account_name'
                })
                continue
            
            # Update settings for this account
            success, error_message = update_account_settings_bulk(
                BASE_DIR, device_id, account_name, settings
            )
            
            if success:
                updated_accounts += 1
            else:
                failed_accounts.append({
                    'account_id': f"{device_id}/{account_name}",
                    'error': error_message
                })
        
        # Log the results
        print(f"Bulk settings update completed:")
        print(f"Updated accounts: {updated_accounts}")
        print(f"Failed accounts: {len(failed_accounts)}")
        
        return jsonify({
            'success': True,
            'updated_accounts': updated_accounts,
            'failed_accounts': failed_accounts
        })
    except Exception as e:
        print(f"Error in bulk settings update: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run Flask app without debug mode to avoid watchdog compatibility issues
    app.run(debug=False, host='0.0.0.0', port=5055)
