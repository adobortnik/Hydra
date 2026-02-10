#!/usr/bin/env python3
"""
Profile Task Manager - Helper script for managing profile update tasks
"""

import sys
import os
from pathlib import Path
import shutil

from profile_automation_db import (
    init_database, add_profile_update_task, get_pending_tasks,
    add_profile_picture, get_profile_pictures, add_bio_template,
    get_bio_templates, get_device_account, PROFILE_PICTURES_DIR
)

def show_menu():
    """Display main menu"""
    print("\n" + "="*70)
    print("PROFILE TASK MANAGER")
    print("="*70)
    print("1. Add new profile update task")
    print("2. View pending tasks")
    print("3. Add profile picture to library")
    print("4. View profile pictures")
    print("5. Add bio template")
    print("6. View bio templates")
    print("7. View device account info")
    print("8. Initialize database")
    print("0. Exit")
    print("="*70)

def add_task_interactive():
    """Interactive task creation"""
    print("\n--- Add New Profile Update Task ---\n")

    # Device serial
    device_serial = input("Enter device serial (e.g., 192.168.101.107_5555): ").strip()
    if not device_serial:
        print("Device serial is required!")
        return

    # Instagram package
    print("\nInstagram package options:")
    print("0. com.instagram.android (Original)")
    for i, letter in enumerate('efghijklmnop', 1):
        print(f"{i}. com.instagram.android{letter}")

    package_choice = input("\nSelect package (0-12) or enter custom: ").strip()
    try:
        package_num = int(package_choice)
        if package_num == 0:
            instagram_package = "com.instagram.android"
        elif 1 <= package_num <= 12:
            letter = chr(ord('e') + package_num - 1)
            instagram_package = f"com.instagram.android{letter}"
        else:
            print("Invalid choice")
            return
    except ValueError:
        instagram_package = package_choice

    # Current username (optional)
    username = input("\nCurrent username (optional, press Enter to skip): ").strip() or None

    # New username
    new_username = input("New username (press Enter to skip): ").strip() or None

    # New bio
    print("\nBio options:")
    print("1. Enter bio manually")
    print("2. Choose from templates")
    print("3. Skip bio change")

    bio_choice = input("Select option (1-3): ").strip()
    new_bio = None

    if bio_choice == "1":
        print("\nEnter bio (press Enter twice to finish):")
        bio_lines = []
        while True:
            line = input()
            if line == "" and bio_lines and bio_lines[-1] == "":
                break
            bio_lines.append(line)
        new_bio = "\n".join(bio_lines[:-1]) if bio_lines else None

    elif bio_choice == "2":
        templates = get_bio_templates()
        if templates:
            print("\nAvailable bio templates:")
            for i, template in enumerate(templates, 1):
                print(f"{i}. {template['name']} (Category: {template['category'] or 'None'})")
                print(f"   {template['bio_text'][:60]}...")

            template_choice = input("\nSelect template number: ").strip()
            try:
                template_idx = int(template_choice) - 1
                if 0 <= template_idx < len(templates):
                    new_bio = templates[template_idx]['bio_text']
                    print(f"Selected bio: {new_bio}")
            except ValueError:
                print("Invalid choice")
        else:
            print("No bio templates available")

    # Profile picture
    print("\nProfile picture options:")
    print("1. Choose from library")
    print("2. Skip profile picture change")

    pic_choice = input("Select option (1-2): ").strip()
    profile_picture_id = None

    if pic_choice == "1":
        # Filter options
        print("\nFilter by gender?")
        print("1. Male")
        print("2. Female")
        print("3. Neutral")
        print("4. All")

        gender_choice = input("Select (1-4): ").strip()
        gender_filter = None
        if gender_choice == "1":
            gender_filter = "male"
        elif gender_choice == "2":
            gender_filter = "female"
        elif gender_choice == "3":
            gender_filter = "neutral"

        pictures = get_profile_pictures(gender=gender_filter)

        if pictures:
            print("\nAvailable profile pictures:")
            for i, pic in enumerate(pictures[:20], 1):  # Show first 20
                print(f"{i}. {pic['filename']} (Gender: {pic['gender'] or 'Unknown'}, "
                      f"Used: {pic['times_used']} times)")

            pic_num = input("\nSelect picture number: ").strip()
            try:
                pic_idx = int(pic_num) - 1
                if 0 <= pic_idx < len(pictures):
                    profile_picture_id = pictures[pic_idx]['id']
                    print(f"Selected: {pictures[pic_idx]['filename']}")
            except ValueError:
                print("Invalid choice")
        else:
            print("No profile pictures available in library")

    # Confirm and create task
    print("\n--- Task Summary ---")
    print(f"Device: {device_serial}")
    print(f"Instagram Package: {instagram_package}")
    print(f"Current Username: {username or 'N/A'}")
    print(f"New Username: {new_username or 'No change'}")
    print(f"New Bio: {new_bio[:50] + '...' if new_bio and len(new_bio) > 50 else new_bio or 'No change'}")
    print(f"Profile Picture ID: {profile_picture_id or 'No change'}")

    confirm = input("\nCreate this task? (y/n): ").strip().lower()

    if confirm == 'y':
        task_id = add_profile_update_task(
            device_serial=device_serial,
            instagram_package=instagram_package,
            username=username,
            new_username=new_username,
            new_bio=new_bio,
            profile_picture_id=profile_picture_id
        )
        print(f"\nTask created successfully! Task ID: {task_id}")
    else:
        print("Task creation cancelled")

def view_pending_tasks():
    """View all pending tasks"""
    tasks = get_pending_tasks()

    if not tasks:
        print("\nNo pending tasks")
        return

    print(f"\n--- Pending Tasks ({len(tasks)}) ---\n")

    for task in tasks:
        print(f"Task ID: {task['id']}")
        print(f"  Device: {task['device_serial']}")
        print(f"  Package: {task['instagram_package']}")
        print(f"  Username: {task['username'] or 'N/A'} → {task['new_username'] or 'No change'}")
        print(f"  Bio: {task['new_bio'][:50] + '...' if task['new_bio'] and len(task['new_bio']) > 50 else task['new_bio'] or 'No change'}")
        print(f"  Picture: {task['filename'] if task['profile_picture_id'] else 'No change'}")
        print(f"  Created: {task['created_at']}")
        print(f"  Status: {task['status']}")
        print()

def add_picture_interactive():
    """Interactive profile picture addition"""
    print("\n--- Add Profile Picture ---\n")

    # File path
    file_path = input("Enter path to image file: ").strip()

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return

    # Get file info
    filename = os.path.basename(file_path)
    print(f"Filename: {filename}")

    # Gender
    print("\nGender category:")
    print("1. Male")
    print("2. Female")
    print("3. Neutral")

    gender_choice = input("Select (1-3): ").strip()
    gender = None
    target_dir = "uploaded"

    if gender_choice == "1":
        gender = "male"
        target_dir = "male"
    elif gender_choice == "2":
        gender = "female"
        target_dir = "female"
    elif gender_choice == "3":
        gender = "neutral"
        target_dir = "neutral"

    # Category
    category = input("\nCategory (e.g., professional, casual, artistic) [optional]: ").strip() or None

    # Style
    style = input("Style description [optional]: ").strip() or None

    # Notes
    notes = input("Notes [optional]: ").strip() or None

    # Copy file to profile_pictures directory
    dest_dir = PROFILE_PICTURES_DIR / target_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    # Handle duplicate filenames
    counter = 1
    while dest_path.exists():
        name, ext = os.path.splitext(filename)
        dest_path = dest_dir / f"{name}_{counter}{ext}"
        counter += 1

    shutil.copy2(file_path, dest_path)
    print(f"Image copied to: {dest_path}")

    # Add to database
    pic_id = add_profile_picture(
        filename=dest_path.name,
        original_path=str(dest_path),
        category=category,
        gender=gender,
        style=style,
        notes=notes
    )

    print(f"\nProfile picture added successfully! ID: {pic_id}")

def view_pictures():
    """View all profile pictures"""
    pictures = get_profile_pictures()

    if not pictures:
        print("\nNo profile pictures in library")
        return

    print(f"\n--- Profile Pictures ({len(pictures)}) ---\n")

    for pic in pictures:
        print(f"ID: {pic['id']}")
        print(f"  Filename: {pic['filename']}")
        print(f"  Path: {pic['original_path']}")
        print(f"  Gender: {pic['gender'] or 'N/A'}")
        print(f"  Category: {pic['category'] or 'N/A'}")
        print(f"  Style: {pic['style'] or 'N/A'}")
        print(f"  Times Used: {pic['times_used']}")
        print(f"  Last Used: {pic['last_used'] or 'Never'}")
        print(f"  Notes: {pic['notes'] or 'N/A'}")
        print()

def add_bio_template_interactive():
    """Interactive bio template addition"""
    print("\n--- Add Bio Template ---\n")

    # Name
    name = input("Template name: ").strip()
    if not name:
        print("Name is required!")
        return

    # Bio text
    print("\nEnter bio text (press Enter twice to finish):")
    bio_lines = []
    while True:
        line = input()
        if line == "" and bio_lines and bio_lines[-1] == "":
            break
        bio_lines.append(line)

    bio_text = "\n".join(bio_lines[:-1]) if bio_lines else ""

    if not bio_text:
        print("Bio text is required!")
        return

    # Category
    category = input("\nCategory (e.g., business, personal, influencer) [optional]: ").strip() or None

    # Add to database
    bio_id = add_bio_template(name, bio_text, category)

    if bio_id:
        print(f"\nBio template added successfully! ID: {bio_id}")
    else:
        print("\nFailed to add bio template (name may already exist)")

def view_bio_templates():
    """View all bio templates"""
    templates = get_bio_templates()

    if not templates:
        print("\nNo bio templates available")
        return

    print(f"\n--- Bio Templates ({len(templates)}) ---\n")

    for template in templates:
        print(f"ID: {template['id']}")
        print(f"  Name: {template['name']}")
        print(f"  Category: {template['category'] or 'N/A'}")
        print(f"  Times Used: {template['times_used']}")
        print(f"  Bio Text:")
        print(f"  {template['bio_text']}")
        print()

def view_device_info():
    """View device account information"""
    device_serial = input("\nEnter device serial: ").strip()

    if not device_serial:
        print("Device serial is required!")
        return

    account = get_device_account(device_serial)

    if not account:
        print(f"\nNo information found for device: {device_serial}")
        return

    print(f"\n--- Device Account Information ---")
    print(f"Device: {device_serial}")
    print(f"Current Username: {account['current_username'] or 'N/A'}")
    print(f"Current Bio: {account['current_bio'] or 'N/A'}")
    print(f"Profile Picture ID: {account['current_profile_picture_id'] or 'N/A'}")
    print(f"Instagram Package: {account['instagram_package'] or 'N/A'}")
    print(f"Last Updated: {account['last_updated']}")

def main():
    """Main entry point"""
    # Initialize database
    init_database()

    while True:
        show_menu()

        try:
            choice = input("\nEnter your choice (0-8): ").strip()

            if choice == "0":
                print("Exiting...")
                break
            elif choice == "1":
                add_task_interactive()
            elif choice == "2":
                view_pending_tasks()
            elif choice == "3":
                add_picture_interactive()
            elif choice == "4":
                view_pictures()
            elif choice == "5":
                add_bio_template_interactive()
            elif choice == "6":
                view_bio_templates()
            elif choice == "7":
                view_device_info()
            elif choice == "8":
                init_database()
                print("Database initialized!")
            else:
                print("Invalid choice. Please try again.")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()
