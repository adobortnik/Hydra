"""
Media Folder Sync Module for The Live House Dashboard
----------------------------------------------------
This module provides functionality to sync a folder on the PC with the dashboard's media library.
It can be imported and used directly in simple_app.py.
"""

import os
import hashlib
import shutil
import logging
import sqlite3
import mimetypes
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class MediaFolderHandler(FileSystemEventHandler):
    """File system event handler for media folder changes"""
    
    def __init__(self, media_dir, db_path, process_existing=False):
        self.media_dir = media_dir
        self.original_dir = os.path.join(media_dir, 'original')
        self.processed_dir = os.path.join(media_dir, 'processed')
        self.db_path = db_path
        
        # Create directories if they don't exist
        os.makedirs(self.original_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        # Process existing files if requested
        if process_existing:
            self.process_directory(self.original_dir)
    
    def on_created(self, event):
        """Handle file or directory creation events"""
        if not event.is_directory and self._is_valid_media_file(event.src_path):
            logger.info(f"New file detected: {event.src_path}")
            # Get parent folder ID if file is in a subdirectory
            parent_dir = os.path.dirname(event.src_path)
            parent_folder_id = None
            if parent_dir != self.original_dir:
                parent_folder_id = self._get_or_create_folder(parent_dir)
            self._process_media_file(event.src_path, parent_folder_id)
        elif event.is_directory and os.path.dirname(event.src_path) != self.processed_dir:
            logger.info(f"New directory detected: {event.src_path}")
            # Get parent folder ID
            parent_dir = os.path.dirname(event.src_path)
            parent_folder_id = None
            if parent_dir != self.original_dir:
                parent_folder_id = self._get_or_create_folder(parent_dir)
            # Create folder in database
            self._get_or_create_folder(event.src_path, parent_folder_id)
    
    def on_moved(self, event):
        """Handle file or folder move/rename events"""
        logger.info(f"Moved/renamed: {event.src_path} -> {event.dest_path}")
        # For simplicity, we'll just process the destination as a new file/folder
        if os.path.isfile(event.dest_path) and self._is_valid_media_file(event.dest_path):
            parent_dir = os.path.dirname(event.dest_path)
            parent_folder_id = None
            if parent_dir != self.original_dir:
                parent_folder_id = self._get_or_create_folder(parent_dir)
            self._process_media_file(event.dest_path, parent_folder_id)
        elif os.path.isdir(event.dest_path):
            self.process_directory(event.dest_path)
    
    def process_directory(self, directory_path, parent_folder_id=None):
        """Process a directory and all its contents"""
        # Skip the processed directory
        if os.path.abspath(directory_path) == os.path.abspath(self.processed_dir):
            return
        
        # Create or get folder ID for this directory
        rel_path = os.path.relpath(directory_path, self.original_dir)
        if rel_path != '.':  # Skip the root directory
            folder_id = self._get_or_create_folder(directory_path, parent_folder_id)
        else:
            folder_id = parent_folder_id
        
        # Process all files in the directory
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            
            if os.path.isfile(item_path) and self._is_valid_media_file(item_path):
                self._process_media_file(item_path, folder_id)
            elif os.path.isdir(item_path) and item_path != self.processed_dir:
                self.process_directory(item_path, folder_id)
    
    def _get_db_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _is_valid_media_file(self, file_path):
        """Check if a file is a valid media file"""
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in valid_extensions
    
    def _get_media_type(self, file_path):
        """Get media type from file extension"""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            if mime_type.startswith('image/'):
                return 'image'
            elif mime_type.startswith('video/'):
                return 'video'
        return 'unknown'
    
    def _generate_file_id(self, file_path):
        """Generate a unique ID for a file based on its content"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    
    def _get_or_create_folder(self, folder_path, parent_id=None):
        """Get or create a folder in the database"""
        folder_name = os.path.basename(folder_path)
        
        conn = self._get_db_connection()
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
    
    def _process_media_file(self, file_path, folder_id=None):
        """Process a media file and add it to the database"""
        if not self._is_valid_media_file(file_path):
            logger.info(f"Skipping non-media file: {file_path}")
            return
        
        # Generate a unique ID for the file
        file_id = self._generate_file_id(file_path)
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_type = self._get_media_type(file_path)
        
        # Define paths in the dashboard structure
        rel_path = os.path.relpath(file_path, self.original_dir)
        target_dir = os.path.dirname(os.path.join(self.original_dir, rel_path))
        os.makedirs(target_dir, exist_ok=True)
        
        target_path = os.path.join(self.original_dir, rel_path)
        
        # Copy file if it's not already in the right location
        if os.path.abspath(file_path) != os.path.abspath(target_path):
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(file_path, target_path)
        
        conn = self._get_db_connection()
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


def start_media_folder_watcher(media_dir, db_path, process_existing=True):
    """Start the media folder watcher"""
    # Initialize event handler
    event_handler = MediaFolderHandler(media_dir, db_path, process_existing)
    
    # Set up file system observer
    observer = Observer()
    observer.schedule(event_handler, os.path.join(media_dir, 'original'), recursive=True)
    observer.start()
    
    logger.info(f"Media folder watcher started. Monitoring: {os.path.join(media_dir, 'original')}")
    logger.info("You can now add files and folders directly to this directory.")
    
    return observer
