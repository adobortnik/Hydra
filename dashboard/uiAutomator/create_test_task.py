#!/usr/bin/env python3
"""
Create a test task for anna.blvv
Quick script to create a standard test task without going through the dashboard
"""

from profile_automation_db import add_profile_update_task
from tag_based_automation import TagBasedAutomation

def create_test_task():
    """
    Create a test task for anna.blvv on device 10.1.10.36_5555
    Based on the last task configuration
    """

    # Get the correct Instagram package from settings.db
    automation = TagBasedAutomation()
    instagram_package = automation._get_instagram_package('10.1.10.36_5555', 'anna.blvv')

    print("="*70)
    print("CREATING TEST TASK")
    print("="*70)
    print(f"\nDevice: 10.1.10.36:5555")
    print(f"Username: anna.blvv")
    print(f"Instagram Package: {instagram_package}")
    print(f"New Username: chantall.private")
    print(f"New Bio: backup acc @chantie.rey")
    print(f"Profile Picture: None")

    # Create the task
    task_id = add_profile_update_task(
        device_serial='10.1.10.36:5555',
        instagram_package=instagram_package,
        username='anna.blvv',
        new_username='chantall.private',
        new_bio='backup acc @chantie.rey',
        profile_picture_id=None
    )

    print(f"\nCreated test task ID: {task_id}")
    print("\nRun the task with:")
    print("  python automated_profile_manager.py")
    print("="*70)

    return task_id

if __name__ == "__main__":
    create_test_task()
