#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Media Folder Watcher for The Live House Dashboard
-------------------------------------------------
This script watches the media_library/original folder for changes and automatically
imports new files and folders into the dashboard's database.
"""

import os
import sys
import time
import sqlite3
import hashlib
import shutil
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import mimetypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(DASHBOARD_DIR, 'data', 'media_library')
ORIGINAL_DIR = os.path.join(MEDIA_DIR, 'original')
PROCESSED_DIR = os.path.join(MEDIA_DIR, 'processed')
DB_PATH = os.path.join(MEDIA_DIR, 'media_library.db')

# Create directories if they don't exist
os.makedirs(ORIGINAL_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Initialize database connection
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Create necessary tables if they don't exist
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create media table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        original_path TEXT NOT NULL,
        processed_path TEXT,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        width INTEGER,
        height INTEGER,
        duration REAL,
        title TEXT,
        description TEXT,
        tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create folders table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        parent_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parent_id) REFERENCES folders (id)
    )
    ''')
    
    # Create media_folders table for many-to-many relationship
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media_folders (
        media_id TEXT,
        folder_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (media_id, folder_id),
        FOREIGN KEY (media_id) REFERENCES media (id),
        FOREIGN KEY (folder_id) REFERENCES folders (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Generate a unique ID for a file based on its content
def generate_file_id(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

# Check if a file is a valid media file
def is_valid_media_file(file_path):
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov']
    _, ext = os.path.splitext(file_path)
    return ext.lower() in valid_extensions

# Get media type from file extension
def get_media_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
    return 'unknown'

# Get or create a folder in the database
def get_or_create_folder(folder_path, parent_id=None):
    folder_name = os.path.basename(folder_path)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if folder exists
    if parent_id:
        cursor.execute('SELECT id FROM folders WHERE name = ? AND parent_id = ?', (folder_name, parent_id))
    else:
        cursor.execute('SELECT id FROM folders WHERE name = ? AND parent_id IS NULL', (folder_name,))
    
    folder = cursor.fetchone()
    
    if folder:
        folder_id = folder['id']
    else:
        # Create new folder
        folder_id = hashlib.md5(folder_path.encode()).hexdigest()
        cursor.execute(
            'INSERT INTO folders (id, name, description, parent_id) VALUES (?, ?, ?, ?)',
            (folder_id, folder_name, f"Auto-imported folder: {folder_name}", parent_id)
        )
        conn.commit()
        logger.info(f"Created new folder: {folder_name}")
    
    conn.close()
    return folder_id

# Process a media file and add it to the database
def process_media_file(file_path, folder_id=None):
    if not is_valid_media_file(file_path):
        logger.info(f"Skipping non-media file: {file_path}")
        return
    
    # Generate a unique ID for the file
    file_id = generate_file_id(file_path)
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_type = get_media_type(file_path)
    
    # Define paths in the dashboard structure
    rel_path = os.path.relpath(file_path, ORIGINAL_DIR)
    target_dir = os.path.dirname(os.path.join(ORIGINAL_DIR, rel_path))
    os.makedirs(target_dir, exist_ok=True)
    
    target_path = os.path.join(ORIGINAL_DIR, rel_path)
    
    # Copy file if it's not already in the right location
    if os.path.abspath(file_path) != os.path.abspath(target_path):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(file_path, target_path)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if media already exists
    cursor.execute('SELECT id FROM media WHERE id = ?', (file_id,))
    existing_media = cursor.fetchone()
    
    if not existing_media:
        # Add new media to database
        cursor.execute(
            'INSERT INTO media (id, filename, original_path, file_type, file_size, title) VALUES (?, ?, ?, ?, ?, ?)',
            (file_id, filename, rel_path, file_type, file_size, os.path.splitext(filename)[0])
        )
        logger.info(f"Added new media: {filename}")
    
    # If folder_id is provided, add media to folder
    if folder_id:
        # Check if media is already in folder
        cursor.execute('SELECT 1 FROM media_folders WHERE media_id = ? AND folder_id = ?', (file_id, folder_id))
        if not cursor.fetchone():
            cursor.execute(
                'INSERT INTO media_folders (media_id, folder_id) VALUES (?, ?)',
                (file_id, folder_id)
            )
            logger.info(f"Added media {filename} to folder {folder_id}")
    
    conn.commit()
    conn.close()

# Process a directory and all its contents
def process_directory(directory_path, parent_folder_id=None):
    # Skip the processed directory
    if os.path.abspath(directory_path) == os.path.abspath(PROCESSED_DIR):
        return
    
    # Create or get folder ID for this directory
    rel_path = os.path.relpath(directory_path, ORIGINAL_DIR)
    if rel_path != '.':  # Skip the root directory
        folder_id = get_or_create_folder(directory_path, parent_folder_id)
    else:
        folder_id = parent_folder_id
    
    # Process all files in the directory
    for item in os.listdir(directory_path):
        item_path = os.path.join(directory_path, item)
        
        if os.path.isfile(item_path):
            process_media_file(item_path, folder_id)
        elif os.path.isdir(item_path):
            process_directory(item_path, folder_id)

# File system event handler
class MediaFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and is_valid_media_file(event.src_path):
            logger.info(f"New file detected: {event.src_path}")
            # Get parent folder ID if file is in a subdirectory
            parent_dir = os.path.dirname(event.src_path)
            parent_folder_id = None
            if parent_dir != ORIGINAL_DIR:
                parent_folder_id = get_or_create_folder(parent_dir)
            process_media_file(event.src_path, parent_folder_id)
        elif event.is_directory and os.path.dirname(event.src_path) != PROCESSED_DIR:
            logger.info(f"New directory detected: {event.src_path}")
            # Get parent folder ID
            parent_dir = os.path.dirname(event.src_path)
            parent_folder_id = None
            if parent_dir != ORIGINAL_DIR:
                parent_folder_id = get_or_create_folder(parent_dir)
            # Create folder in database
            get_or_create_folder(event.src_path, parent_folder_id)
    
    def on_moved(self, event):
        # Handle file/folder renames or moves
        logger.info(f"Moved/renamed: {event.src_path} -> {event.dest_path}")
        # For simplicity, we'll just process the destination as a new file/folder
        if os.path.isfile(event.dest_path) and is_valid_media_file(event.dest_path):
            parent_dir = os.path.dirname(event.dest_path)
            parent_folder_id = None
            if parent_dir != ORIGINAL_DIR:
                parent_folder_id = get_or_create_folder(parent_dir)
            process_media_file(event.dest_path, parent_folder_id)
        elif os.path.isdir(event.dest_path):
            process_directory(event.dest_path)

def main():
    # Initialize database
    initialize_database()
    
    # Process existing files and folders
    logger.info("Processing existing files and folders...")
    process_directory(ORIGINAL_DIR)
    
    # Set up file system observer
    event_handler = MediaFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, ORIGINAL_DIR, recursive=True)
    observer.start()
    
    logger.info(f"Media folder watcher started. Monitoring: {ORIGINAL_DIR}")
    logger.info("You can now add files and folders directly to this directory.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
