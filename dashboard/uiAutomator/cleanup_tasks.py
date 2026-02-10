#!/usr/bin/env python3
"""
Clean up task queue - keep only one test task
"""

import sqlite3
from pathlib import Path
from profile_automation_db import PROFILE_AUTOMATION_DB

def cleanup_tasks(keep_count=1):
    """
    Delete all pending tasks except for the specified number

    Args:
        keep_count: Number of tasks to keep (default: 1)
    """
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    # Get all pending tasks
    cursor.execute('''
        SELECT id, device_serial, username, instagram_package, status
        FROM profile_updates
        WHERE status = 'pending'
        ORDER BY created_at ASC
    ''')

    tasks = cursor.fetchall()

    print(f"Found {len(tasks)} pending tasks")

    if len(tasks) == 0:
        print("No tasks to clean up!")
        conn.close()
        return

    # Show the tasks we'll keep
    if len(tasks) <= keep_count:
        print(f"\nOnly {len(tasks)} task(s) found. Nothing to delete.")
        conn.close()
        return

    print(f"\nKeeping first {keep_count} task(s):")
    for i in range(min(keep_count, len(tasks))):
        task_id, device, username, package, status = tasks[i]
        print(f"  Task {task_id}: {device}/{username} ({package})")

    # Delete the rest
    tasks_to_delete = tasks[keep_count:]
    print(f"\nDeleting {len(tasks_to_delete)} task(s)...")

    for task_id, device, username, package, status in tasks_to_delete:
        cursor.execute('DELETE FROM profile_updates WHERE id = ?', (task_id,))
        print(f"  Deleted Task {task_id}: {device}/{username}")

    conn.commit()
    conn.close()

    print(f"\n✅ Done! Kept {keep_count} task(s), deleted {len(tasks_to_delete)} task(s)")

def delete_all_tasks():
    """Delete ALL tasks (pending, completed, failed)"""
    conn = sqlite3.connect(PROFILE_AUTOMATION_DB)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM profile_updates')
    total = cursor.fetchone()[0]

    if total == 0:
        print("No tasks to delete!")
        conn.close()
        return

    response = input(f"\n⚠️  Delete ALL {total} tasks? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        conn.close()
        return

    cursor.execute('DELETE FROM profile_updates')
    conn.commit()
    conn.close()

    print(f"✅ Deleted all {total} tasks")

if __name__ == "__main__":
    import sys

    print("="*70)
    print("TASK CLEANUP UTILITY")
    print("="*70)

    if len(sys.argv) > 1:
        if sys.argv[1] == '--all':
            delete_all_tasks()
        elif sys.argv[1] == '--keep':
            try:
                keep_count = int(sys.argv[2])
                cleanup_tasks(keep_count)
            except (IndexError, ValueError):
                print("Usage: python cleanup_tasks.py --keep <number>")
        else:
            print("Usage:")
            print("  python cleanup_tasks.py          # Keep 1 task, delete rest")
            print("  python cleanup_tasks.py --keep 5 # Keep 5 tasks, delete rest")
            print("  python cleanup_tasks.py --all    # Delete ALL tasks")
    else:
        # Default: keep 1 task
        cleanup_tasks(keep_count=1)
