"""
login_task_manager.py

Interactive CLI Manager for Instagram Login Automation
Follows the same pattern as profile_task_manager.py

Features:
- Create login tasks manually
- View pending/completed tasks
- Test 2FA integration
- Process tasks (launch batch processor)

Author: Claude Code
Created: 2025-11-21
"""

import sys
import os
from pathlib import Path
import json
import sqlite3

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from login_automation_db import (
    init_database,
    create_login_task,
    get_all_login_tasks,
    get_pending_login_tasks,
    add_2fa_token,
    get_2fa_token,
    get_statistics,
    delete_task,
    clear_completed_tasks
)
from two_fa_live_client import TwoFALiveClient


# Base directory (2 levels up from uiAutomator, now inside dashboard)
BASE_DIR = Path(__file__).parent.parent.parent


def print_header(title):
    """Print a formatted header"""
    print("\n" + "="*70)
    print(title.center(70))
    print("="*70)


def print_menu(title, options):
    """
    Print a menu with options

    Args:
        title: Menu title
        options: List of (number, description) tuples
    """
    print("\n" + "-"*70)
    print(title)
    print("-"*70)
    for num, desc in options:
        print(f"{num}. {desc}")
    print("-"*70)


def get_user_choice(prompt, valid_choices):
    """
    Get user input with validation

    Args:
        prompt: Input prompt
        valid_choices: List of valid choices

    Returns:
        str: User's choice
    """
    while True:
        choice = input(f"\n{prompt}: ").strip()
        if choice in valid_choices:
            return choice
        print(f"[X] Invalid choice. Please enter one of: {', '.join(valid_choices)}")


def scan_devices():
    """
    Scan for available devices by reading device folders

    Returns:
        list: List of device serials
    """
    print("\nScanning for devices...")

    devices = []
    device_patterns = ["192.168.*_*", "10.1.*.*_*"]

    for pattern in device_patterns:
        for device_dir in BASE_DIR.glob(pattern):
            if device_dir.is_dir():
                devices.append(device_dir.name)

    if devices:
        print(f"[OK] Found {len(devices)} device(s)")
    else:
        print("[!] No devices found")

    return sorted(devices)


def get_device_accounts(device_serial):
    """
    Get all accounts for a device

    Args:
        device_serial: Device serial (e.g., "10.1.10.183_5555")

    Returns:
        list: List of (username, password, instagram_package) tuples
    """
    accounts = []

    device_path = BASE_DIR / device_serial

    if not device_path.exists():
        print(f"[X] Device path not found: {device_path}")
        return accounts

    # Read from accounts.db if exists
    accounts_db = device_path / "accounts.db"

    if accounts_db.exists():
        try:
            conn = sqlite3.connect(accounts_db)
            cursor = conn.cursor()
            cursor.execute("SELECT account, password FROM accounts")
            for row in cursor.fetchall():
                username = row[0]
                password = row[1]

                # Get Instagram package from settings.db
                settings_db = device_path / username / "settings.db"
                instagram_package = "com.instagram.android"  # Default

                if settings_db.exists():
                    try:
                        settings_conn = sqlite3.connect(settings_db)
                        settings_cursor = settings_conn.cursor()
                        settings_cursor.execute("SELECT settings FROM accountsettings WHERE id = 1")
                        settings_row = settings_cursor.fetchone()

                        if settings_row and settings_row[0]:
                            settings_json = json.loads(settings_row[0])
                            app_cloner = settings_json.get('app_cloner', '')
                            if '/' in app_cloner:
                                instagram_package = app_cloner.split('/')[0]

                        settings_conn.close()
                    except Exception as e:
                        print(f"[!] Could not read settings for {username}: {e}")

                accounts.append((username, password, instagram_package))

            conn.close()
        except Exception as e:
            print(f"[X] Error reading accounts.db: {e}")

    return accounts


def create_task_interactive():
    """Create a login task interactively"""
    print_header("CREATE LOGIN TASK")

    # Get device
    devices = scan_devices()

    if not devices:
        print("\n[X] No devices found. Make sure device folders exist.")
        return

    print("\nAvailable Devices:")
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device}")

    choice = get_user_choice(
        "Select device (number)",
        [str(i) for i in range(1, len(devices) + 1)]
    )
    device_serial = devices[int(choice) - 1]

    print(f"\n[OK] Selected device: {device_serial}")

    # Get accounts for this device
    accounts = get_device_accounts(device_serial)

    if not accounts:
        print(f"\n[!] No accounts found for device {device_serial}")
        print("You can still create a task by entering details manually.")

        username = input("\nEnter username: ").strip()
        password = input("Enter password: ").strip()
        instagram_package = input("Enter Instagram package (or press Enter for default): ").strip() or "com.instagram.android"
    else:
        print(f"\nFound {len(accounts)} account(s) on {device_serial}:")
        for i, (user, _, pkg) in enumerate(accounts, 1):
            print(f"{i}. {user} ({pkg})")

        print(f"{len(accounts) + 1}. Enter manually")

        choice = get_user_choice(
            "Select account (number)",
            [str(i) for i in range(1, len(accounts) + 2)]
        )

        if int(choice) == len(accounts) + 1:
            # Manual entry
            username = input("\nEnter username: ").strip()
            password = input("Enter password: ").strip()
            instagram_package = input("Enter Instagram package (or press Enter for default): ").strip() or "com.instagram.android"
        else:
            # Use existing account
            username, password, instagram_package = accounts[int(choice) - 1]
            print(f"\n[OK] Selected account: {username}")

    # 2FA token
    has_2fa = get_user_choice("\nDoes this account use 2FA? (y/n)", ["y", "n", "Y", "N"])

    two_fa_token = None
    if has_2fa.lower() == 'y':
        two_fa_token = input("Enter 2fa.live token: ").strip()

        if two_fa_token:
            # Save token to database
            add_2fa_token(two_fa_token, username=username, device_serial=device_serial)

    # Priority
    priority = input("\nEnter priority (0=normal, higher=sooner) [0]: ").strip() or "0"

    # Create task
    print("\nCreating task...")
    task_id = create_login_task(
        device_serial=device_serial,
        instagram_package=instagram_package,
        username=username,
        password=password,
        two_fa_token=two_fa_token,
        priority=int(priority)
    )

    print(f"\n[OK] Task created successfully! Task ID: {task_id}")


def view_tasks():
    """View all tasks"""
    print_header("VIEW TASKS")

    print_menu("Filter Options", [
        ("1", "All tasks"),
        ("2", "Pending tasks"),
        ("3", "Completed tasks"),
        ("4", "Failed tasks"),
        ("5", "Needs manual intervention"),
    ])

    choice = get_user_choice("Select filter", ["1", "2", "3", "4", "5"])

    status_map = {
        "1": None,
        "2": "pending",
        "3": "completed",
        "4": "failed",
        "5": "needs_manual"
    }

    status = status_map[choice]
    tasks = get_all_login_tasks(status=status)

    if not tasks:
        print(f"\n[OK] No tasks found (filter: {status or 'all'})")
        return

    print(f"\n[OK] Found {len(tasks)} task(s)")
    print("\n" + "-"*70)

    for task in tasks:
        print(f"\nTask ID: {task['id']}")
        print(f"  Device: {task['device_serial']}")
        print(f"  Username: {task['username']}")
        print(f"  Package: {task['instagram_package']}")
        print(f"  Status: {task['status']}")
        print(f"  2FA: {'Yes' if task['two_fa_token'] else 'No'}")
        print(f"  Priority: {task['priority']}")
        print(f"  Retry: {task['retry_count']} / {task['max_retries']}")
        print(f"  Created: {task['created_at']}")

        if task['error_message']:
            print(f"  Error: {task['error_message']}")

        if task['completed_at']:
            print(f"  Completed: {task['completed_at']}")

    print("\n" + "-"*70)


def test_2fa():
    """Test 2FA integration"""
    print_header("TEST 2FA INTEGRATION")

    token = input("\nEnter 2fa.live token: ").strip()

    if not token:
        print("[X] No token provided")
        return

    print(f"\nTesting token: {token}")

    client = TwoFALiveClient(token)

    # Test connection
    print("\n1. Testing connection...")
    result = client.test_connection()

    print(f"\nResult: {result['message']}")

    if result['success']:
        print("[OK] Connection successful")

        if result['code']:
            print(f"[OK] Code available: {result['code']}")
        else:
            # Try to fetch code
            print("\n2. Attempting to fetch code (will retry for up to 30s)...")
            code = client.get_code(max_retries=10, retry_interval=3)

            if code:
                print(f"\n[OK] Code retrieved: {code}")
            else:
                print("\n[!] Could not retrieve code")
    else:
        print(f"[X] Connection failed: {result['message']}")


def process_tasks():
    """Launch the batch processor"""
    print_header("PROCESS TASKS")

    pending = get_pending_login_tasks()

    if not pending:
        print("\n[OK] No pending tasks to process")
        return

    print(f"\n[OK] Found {len(pending)} pending task(s)")

    # Show summary
    devices = set(task['device_serial'] for task in pending)
    print(f"\nDevices: {len(devices)}")
    for device in sorted(devices):
        device_tasks = [t for t in pending if t['device_serial'] == device]
        print(f"  {device}: {len(device_tasks)} task(s)")

    confirm = get_user_choice("\nProcess all pending tasks? (y/n)", ["y", "n", "Y", "N"])

    if confirm.lower() != 'y':
        print("[X] Cancelled")
        return

    print("\n" + "="*70)
    print("LAUNCHING BATCH PROCESSOR")
    print("="*70)

    # Import and run batch processor
    from automated_login_manager import AutomatedLoginManager

    manager = AutomatedLoginManager()
    stats = manager.run_batch_processor()

    print("\n[OK] Batch processing complete!")


def manage_2fa_tokens():
    """Manage 2FA tokens"""
    print_header("MANAGE 2FA TOKENS")

    print_menu("Options", [
        ("1", "Add new token"),
        ("2", "View saved tokens"),
        ("3", "Test a token"),
    ])

    choice = get_user_choice("Select option", ["1", "2", "3"])

    if choice == "1":
        # Add token
        token = input("\nEnter 2fa.live token: ").strip()
        username = input("Enter username (optional): ").strip() or None
        device_serial = input("Enter device serial (optional): ").strip() or None
        phone_number = input("Enter phone number (optional): ").strip() or None
        notes = input("Enter notes (optional): ").strip() or None

        add_2fa_token(token, phone_number, username, device_serial, notes)
        print("\n[OK] Token added successfully!")

    elif choice == "2":
        # View tokens
        from login_automation_db import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM two_factor_services ORDER BY created_at DESC")
        tokens = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not tokens:
            print("\n[OK] No tokens saved")
            return

        print(f"\n[OK] Found {len(tokens)} token(s)")
        print("\n" + "-"*70)

        for token in tokens:
            print(f"\nToken: {token['token']}")
            if token['username']:
                print(f"  Username: {token['username']}")
            if token['device_serial']:
                print(f"  Device: {token['device_serial']}")
            if token['phone_number']:
                print(f"  Phone: {token['phone_number']}")
            print(f"  Status: {token['status']}")
            print(f"  Usage Count: {token['usage_count']}")
            print(f"  Created: {token['created_at']}")
            if token['last_used']:
                print(f"  Last Used: {token['last_used']}")
            if token['notes']:
                print(f"  Notes: {token['notes']}")

        print("\n" + "-"*70)

    elif choice == "3":
        # Test token
        test_2fa()


def view_statistics():
    """View statistics"""
    print_header("STATISTICS")

    stats = get_statistics()

    print("\nTask Statistics:")
    for status, count in stats['tasks'].items():
        print(f"  {status.capitalize()}: {count}")

    print(f"\nLogin Attempts:")
    print(f"  Total: {stats['total_attempts']}")
    print(f"  Successful: {stats['successful_attempts']}")
    print(f"  Success Rate: {stats['success_rate']}%")

    print(f"\n2FA Tokens:")
    print(f"  Active: {stats['active_2fa_tokens']}")

    print(f"\nRecent Activity:")
    print(f"  Logins (24h): {stats['recent_logins_24h']}")


def delete_task_interactive():
    """Delete a task interactively"""
    print_header("DELETE TASK")

    task_id = input("\nEnter task ID to delete: ").strip()

    if not task_id.isdigit():
        print("[X] Invalid task ID")
        return

    confirm = get_user_choice(f"Delete task #{task_id}? (y/n)", ["y", "n", "Y", "N"])

    if confirm.lower() != 'y':
        print("[X] Cancelled")
        return

    if delete_task(int(task_id)):
        print(f"\n[OK] Task #{task_id} deleted")
    else:
        print(f"\n[X] Task #{task_id} not found")


def main_menu():
    """Main menu loop"""
    print_header("INSTAGRAM LOGIN AUTOMATION - TASK MANAGER")

    while True:
        print_menu("Main Menu", [
            ("1", "Create login task"),
            ("2", "View tasks"),
            ("3", "Process tasks (batch processor)"),
            ("4", "Manage 2FA tokens"),
            ("5", "View statistics"),
            ("6", "Delete task"),
            ("7", "Clear completed tasks"),
            ("8", "Test 2FA integration"),
            ("0", "Exit"),
        ])

        choice = get_user_choice("Select option", ["0", "1", "2", "3", "4", "5", "6", "7", "8"])

        if choice == "0":
            print("\n[OK] Goodbye!")
            break
        elif choice == "1":
            create_task_interactive()
        elif choice == "2":
            view_tasks()
        elif choice == "3":
            process_tasks()
        elif choice == "4":
            manage_2fa_tokens()
        elif choice == "5":
            view_statistics()
        elif choice == "6":
            delete_task_interactive()
        elif choice == "7":
            days = input("\nDelete completed tasks older than how many days? [7]: ").strip() or "7"
            clear_completed_tasks(int(days))
        elif choice == "8":
            test_2fa()


if __name__ == '__main__':
    # Initialize database if needed
    if not Path(BASE_DIR / 'uiAutomator' / 'login_automation.db').exists():
        print("Database not found, initializing...")
        init_database()

    main_menu()
